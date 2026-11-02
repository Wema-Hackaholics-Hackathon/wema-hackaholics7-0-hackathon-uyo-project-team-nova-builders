"""Request logs for the business console (Request logs page, API-requests chart).

Every call to /api/open/v1/* gets a `FOID-Request-Id` header. If the call can be
tied to an organisation's key it's stored: method, path (no query string), status,
latency and the key's hint. Bodies and personal data are never stored. Calls with
a missing or unknown key can't be attributed to anyone, so they aren't stored.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response
from sqlmodel import select

from app.core.crypto import sha256_hex
from app.models import ApiKey, ApiRequestLog

OPEN_PREFIX = "/api/open"
RETENTION = timedelta(days=30)


def new_request_id() -> str:
    return "req_" + secrets.token_hex(8)


async def _attribute(request: Request) -> tuple[str, str, str | None, str | None] | None:
    """(org_id, env, key_id, key_hint) — from the auth dependency, or (for 429s raised before it ran) the key hash."""
    st = request.state
    if getattr(st, "api_org_id", None):
        return st.api_org_id, st.api_env, st.api_key_id, getattr(st, "api_key_hint", None)
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    from app.config import _get_session_factory
    async with _get_session_factory()() as db:
        key = (await db.exec(select(ApiKey).where(ApiKey.key_hash == sha256_hex(auth[7:].strip())))).first()
    return (key.org_id, key.env, key.id, key.prefix) if key else None


async def record(request: Request, status: int, latency_ms: int, request_id: str) -> None:
    who = await _attribute(request)
    if who is None:
        return
    org_id, env, key_id, hint = who
    from app.config import _get_session_factory
    async with _get_session_factory()() as db:
        db.add(ApiRequestLog(org_id=org_id, env=env, key_id=key_id, key_hint=hint, request_id=request_id,
                             method=request.method, path=request.url.path.removeprefix(OPEN_PREFIX)[:300],
                             status=status, latency_ms=latency_ms))
        await db.commit()


async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if not request.url.path.startswith(OPEN_PREFIX + "/"):
        return await call_next(request)
    request_id = new_request_id()
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["FOID-Request-Id"] = request_id
    try:
        await record(request, response.status_code, round((time.perf_counter() - start) * 1000), request_id)
    except Exception as exc:   # logging must never break the API call
        print(f"[request-log] not recorded: {exc}", flush=True)
    return response


def log_out(r: ApiRequestLog) -> dict[str, Any]:
    from app.services.checks_service import iso
    return {"request_id": r.request_id, "method": r.method, "path": r.path, "status": r.status,
            "latency_ms": r.latency_ms, "key_hint": r.key_hint, "env": r.env, "created_at": iso(r.created_at)}


def cutoff(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - RETENTION
