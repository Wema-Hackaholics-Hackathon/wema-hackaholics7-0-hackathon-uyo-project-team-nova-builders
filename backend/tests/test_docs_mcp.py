"""The FOID docs MCP server (POST /mcp): JSON-RPC handshake, tools, notifications, origin check."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import get_settings
from app.services import docs_mcp

SITE = "https://docs.foid.ng"
DOCS = {"site": SITE, "pages": [
    {"path": "/guide/webhooks.md", "title": "Webhooks", "section": "Developer guides", "url": f"{SITE}/guide/webhooks",
     "markdown": "# Webhooks\n\nFOID posts events to your endpoint.\n\n## Verify the signature\n\n"
                 "Check the FOID-Signature header with verifyWebhook in Node or verify_webhook in Python.\n\n"
                 "```js\n## not a heading\n```\n\n## Retries\n\nFailed deliveries are retried with backoff.\n"},
    {"path": "/sdks/python.md", "title": "Python — foid", "section": "SDKs", "url": f"{SITE}/sdks/python",
     "markdown": "# Python — foid\n\nInstall the SDK.\n\n## Exchange a code\n\nfoid.oauth.exchange(code, code_verifier)\n"},
    {"path": "/guide/index.md", "title": "Introduction", "section": "Developer guides", "url": f"{SITE}/guide/",
     "markdown": "# Introduction\n\nWhat FOID is.\n"},
]}


@pytest.fixture(autouse=True)
def docs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake() -> dict[str, Any]:
        return DOCS
    monkeypatch.setattr(docs_mcp, "fetch_index", fake)
    monkeypatch.setattr(docs_mcp, "_cache", None)


async def rpc(client: httpx.AsyncClient, method: str, params: dict[str, Any] | None = None, id_: int | None = 1,
              **kw: Any) -> httpx.Response:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    if id_ is not None:
        msg["id"] = id_
    return await client.post("/mcp", json=msg, headers={"Accept": "application/json, text/event-stream", **kw})


async def call(client: httpx.AsyncClient, tool: str, **args: Any) -> dict[str, Any]:
    r = await rpc(client, "tools/call", {"name": tool, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()["result"]


async def test_handshake_and_tool_list(client: httpx.AsyncClient) -> None:
    r = await rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "1"}})
    res = r.json()["result"]
    assert res["protocolVersion"] == "2025-06-18" and res["serverInfo"]["name"] == "foid-docs"
    assert "tools" in res["capabilities"] and "search_foid_docs" in res["instructions"]
    old = (await rpc(client, "initialize", {"protocolVersion": "1999-01-01"})).json()["result"]
    assert old["protocolVersion"] == "2025-06-18"                       # we answer with what we support
    n = await rpc(client, "notifications/initialized", id_=None)
    assert n.status_code == 202 and n.content == b""
    assert (await rpc(client, "ping")).json()["result"] == {}
    tools = (await rpc(client, "tools/list")).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"search_foid_docs", "read_foid_doc", "list_foid_docs"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


async def test_search_ranks_sections_and_skips_code_headings(client: httpx.AsyncClient) -> None:
    res = await call(client, "search_foid_docs", query="verify webhook signature node")
    top = res["structuredContent"]["results"][0]
    assert top["title"] == "Webhooks › Verify the signature" and top["url"] == f"{SITE}/guide/webhooks#verify-the-signature"
    assert top["path"] == "/guide/webhooks.md" and "verifyWebhook" in top["excerpt"]
    assert not any("not a heading" in r["title"] for r in res["structuredContent"]["results"])
    none = await call(client, "search_foid_docs", query="zzzz qqqq")
    assert "No FOID docs matched" in none["content"][0]["text"] and not none["isError"]
    empty = await call(client, "search_foid_docs", query="  ")
    assert empty["isError"]


async def test_read_and_list(client: httpx.AsyncClient) -> None:
    for ref in ("/sdks/python", "sdks/python.md", f"{SITE}/sdks/python#exchange-a-code"):
        page = await call(client, "read_foid_doc", path=ref)
        assert not page["isError"] and "foid.oauth.exchange" in page["content"][0]["text"], ref
    assert "Introduction" in (await call(client, "read_foid_doc", path="/guide/"))["content"][0]["text"]
    missing = await call(client, "read_foid_doc", path="/nope")
    assert missing["isError"]
    listing = (await call(client, "list_foid_docs"))["content"][0]["text"]
    assert "## Developer guides" in listing and "/sdks/python.md" in listing


async def test_protocol_errors(client: httpx.AsyncClient) -> None:
    assert (await rpc(client, "resources/list")).json()["error"]["code"] == -32601
    assert (await rpc(client, "tools/call", {"name": "drop_db", "arguments": {}})).json()["error"]["code"] == -32602
    bad = await client.post("/mcp", content=b"{not json", headers={"Content-Type": "application/json"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32700
    assert (await client.post("/mcp", json={"id": 1, "method": "ping"})).json()["error"]["code"] == -32600
    assert (await client.get("/mcp")).status_code == 405


async def test_browser_origin_must_be_ours(client: httpx.AsyncClient) -> None:
    assert (await rpc(client, "ping", Origin="https://evil.example")).status_code == 403
    assert (await rpc(client, "ping", Origin=get_settings().DOCS_SITE_URL)).status_code == 200


async def test_docs_site_down_is_a_tool_error(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def down() -> dict[str, Any]:
        raise docs_mcp.DocsUnavailable("Couldn't load the FOID docs")
    monkeypatch.setattr(docs_mcp, "fetch_index", down)
    res = await call(client, "search_foid_docs", query="webhooks")
    assert res["isError"] and "Couldn't load" in res["content"][0]["text"]


async def test_switched_off(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "DOCS_MCP", False)
    assert (await rpc(client, "ping")).status_code == 404
