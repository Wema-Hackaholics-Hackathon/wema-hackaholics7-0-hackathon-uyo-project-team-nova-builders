"""FOID docs MCP server — POST /mcp (Model Context Protocol, Streamable HTTP, stateless, JSON responses).

Lets AI tools (Claude, ChatGPT, Cursor, VS Code, …) search and read the FOID developer docs:

    claude mcp add --transport http foid-docs http://localhost:8000/mcp

Tools: search_foid_docs, read_foid_doc, list_foid_docs. Read-only, no auth, nothing about any person or
business — only the public docs. Switch off with DOCS_MCP=false.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.services import docs_mcp as dm
from app.utils.limiter import limiter

router = APIRouter(tags=["mcp"])

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
SERVER_INFO = {"name": "foid-docs", "title": "FOID Docs", "version": "0.1.0"}
INSTRUCTIONS = (
    "Search and read the FOID developer documentation: Continue with FOID (OAuth 2.0 + PKCE sign-in), hosted "
    "identity verification, NIN/BVN checks, subjects and consent, webhooks, the Python/Node/React SDKs, the Open "
    "API reference, and help for FOID users. Use search_foid_docs first, then read_foid_doc for the full page. "
    "Quote code from the docs rather than guessing SDK or API names."
)
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {
        "name": "search_foid_docs",
        "title": "Search FOID docs",
        "description": "Search the FOID developer docs, SDK reference, API reference and user help. Returns the "
                       "best-matching sections with an excerpt and a link. Use read_foid_doc to get a whole page.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What you're looking for, e.g. 'verify webhook signature in node'"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}},
            "required": ["query"], "additionalProperties": False},
        "annotations": READ_ONLY,
    },
    {
        "name": "read_foid_doc",
        "title": "Read a FOID docs page",
        "description": "The full markdown of one docs page. Pass a path from search_foid_docs or list_foid_docs, "
                       "e.g. '/guide/continue-with-foid', '/sdks/python.md' or a docs URL.",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}},
                        "required": ["path"], "additionalProperties": False},
        "annotations": READ_ONLY,
    },
    {
        "name": "list_foid_docs",
        "title": "List FOID docs pages",
        "description": "Every page in the FOID docs, grouped by section, with its path.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": READ_ONLY,
    },
]


def _result(id_: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _text(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


async def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        ix = await dm.index()
    except dm.DocsUnavailable as e:
        return _text(f"{e} The docs site may be down — try again later.", is_error=True)

    if name == "search_foid_docs":
        query = str(args.get("query", "")).strip()
        if not query:
            return _text("Pass a non-empty query.", is_error=True)
        try:
            limit = max(1, min(int(args.get("limit", 5)), 10))
        except (TypeError, ValueError):
            limit = 5
        hits = dm.search(ix, query, limit)
        if not hits:
            return _text(f'No FOID docs matched "{query}". Try other words, or list_foid_docs to browse.')
        parts = [f"## {h['title']}\n{h['section']} · {h['url']} · read_foid_doc path: {h['path']}\n\n{h['excerpt']}" for h in hits]
        return {**_text("\n\n---\n\n".join(parts)), "structuredContent": {"results": hits}}

    if name == "read_foid_doc":
        page = dm.find_page(ix, str(args.get("path", "")))
        if page is None:
            return _text(f"No docs page at {args.get('path')!r}. Use list_foid_docs to see the paths.", is_error=True)
        return _text(f"Source: {page['url']}\n\n{page['markdown']}")

    if name == "list_foid_docs":
        lines: list[str] = []
        for section in dict.fromkeys(p["section"] for p in ix.pages):
            lines.append(f"## {section}")
            lines += [f"- {p['title']} — {p['path']}" for p in ix.pages if p["section"] == section]
            lines.append("")
        return _text("\n".join(lines).strip())

    raise KeyError(name)


async def _handle(msg: Any) -> dict[str, Any] | None:
    """One JSON-RPC message → a response, or None for notifications."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    method, id_, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:            # notification (e.g. notifications/initialized): no reply
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(id_, {
            "protocolVersion": asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(args, dict):
            return _error(id_, -32602, "arguments must be an object")
        try:
            return _result(id_, await _call_tool(str(name), args))
        except KeyError:
            return _error(id_, -32602, f"Unknown tool: {name}")
    return _error(id_, -32601, f"Method not found: {method}")


def _origin_ok(request: Request) -> bool:
    """MCP spec: validate Origin (DNS-rebinding protection). AI clients send none; browsers must be ours."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    s = get_settings()
    allowed = {o.strip().rstrip("/") for o in s.ALLOWED_ORIGINS.split(",") if o.strip()} | {s.DOCS_SITE_URL.rstrip("/")}
    return origin.rstrip("/") in allowed


@router.post("/mcp")
@limiter.limit("120/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def mcp(request: Request) -> Response:
    if not get_settings().DOCS_MCP:
        return JSONResponse(_error(None, -32601, "The FOID docs MCP server is switched off"), status_code=404)
    if not _origin_ok(request):
        return JSONResponse(_error(None, -32600, "Origin not allowed"), status_code=403)
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
    if isinstance(body, list):     # older clients may batch
        replies = [r for r in [await _handle(m) for m in body] if r is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await _handle(body)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.get("/mcp")
async def mcp_get() -> Response:
    """No server-initiated stream: this server only answers requests."""
    return Response(status_code=405, headers={"Allow": "POST"})
