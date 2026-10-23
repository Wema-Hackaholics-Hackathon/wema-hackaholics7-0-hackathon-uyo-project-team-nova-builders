"""Mono Open Banking service — thin async wrapper.

Uses the Mono REST API with MONO_SECRET_KEY from settings.
All methods raise httpx.HTTPStatusError on non-2xx responses
(callers should let this propagate to FastAPI's exception handler,
or catch it and translate to an appropriate HTTP status code).

Mono sandbox base URL: https://api.withmono.com
"""

from __future__ import annotations

import httpx

from ..config import get_settings

_BASE = "https://api.withmono.com"
_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def _headers() -> dict[str, str]:
    return {
        "mono-sec-key": get_settings().MONO_SECRET_KEY,
        "Content-Type": "application/json",
    }


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_BASE, timeout=_TIMEOUT)


async def exchange_code(code: str) -> dict[str, object]:
    """Exchange a Mono Connect code for an account ID.

    POST /v2/accounts/auth  →  { "status": "successful", "data": { "id": "<mono_account_id>", ... } }
    """
    async with _client() as client:
        r = await client.post("/v2/accounts/auth", json={"code": code}, headers=_headers())
        _ = r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


async def get_account(account_id: str) -> dict[str, object]:
    """Fetch current account details (balance, status, institution name, etc.).

    GET /v2/accounts/{account_id}
    """
    async with _client() as client:
        r = await client.get(f"/v2/accounts/{account_id}", headers=_headers())
        _ = r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


async def get_transactions(
    account_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    page: int = 1,
) -> dict[str, object]:
    """Fetch paginated transactions for an account.

    GET /v2/accounts/{account_id}/transactions
    Query params: start (YYYY-MM-DD), end (YYYY-MM-DD), limit, page
    """
    params: dict[str, str | int] = {"limit": limit, "page": page}
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    async with _client() as client:
        r = await client.get(
            f"/v2/accounts/{account_id}/transactions",
            params=params,
            headers=_headers(),
        )
        _ = r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
