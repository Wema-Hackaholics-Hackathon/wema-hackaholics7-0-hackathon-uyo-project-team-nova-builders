"""Authentication for the public Open API (/api/open/v1/*).

    Authorization: Bearer sk_test_...   (sandbox: mock providers, never billed)
    Authorization: Bearer sk_live_...   (live: only after FOID approves the business — KYB)

Keys are stored as SHA-256 hashes; the raw key is shown once at creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.crypto import new_token, sha256_hex
from app.models import ApiKey, Organisation

KEY_PREFIX = {"test": "sk_test_", "live": "sk_live_"}


@dataclass
class ApiContext:
    org: Organisation
    env: str
    key: ApiKey


def generate_api_key(env: str) -> tuple[str, str, str]:
    """Return (raw_key, display_prefix, key_hash)."""
    raw = new_token(KEY_PREFIX[env], 32)
    return raw, raw[: len(KEY_PREFIX[env]) + 6], sha256_hex(raw)


def rate_limit_key(request: Request) -> str:
    """slowapi key: per API key (hashed), falling back to client IP."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return "key:" + sha256_hex(auth[7:].strip())[:32]
    return "ip:" + (request.client.host if request.client else "unknown")


async def get_api_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiContext:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ApiError(401, "missing_api_key", "Send your secret key as 'Authorization: Bearer sk_...'")
    raw = auth[7:].strip()
    env = "live" if raw.startswith(KEY_PREFIX["live"]) else "test" if raw.startswith(KEY_PREFIX["test"]) else None
    if env is None:
        raise ApiError(401, "invalid_api_key", "Unrecognised API key format")

    key = (await db.exec(select(ApiKey).where(ApiKey.key_hash == sha256_hex(raw)))).first()
    if key is None or key.revoked_at is not None:
        raise ApiError(401, "invalid_api_key", "API key is invalid or has been revoked")
    org = await db.get(Organisation, key.org_id)
    if org is None or org.status != "active":
        raise ApiError(403, "organisation_suspended", "This organisation is not active")
    if env == "live" and not org.live_enabled:
        raise ApiError(403, "live_mode_disabled", "Live mode is not enabled yet — complete business verification (KYB)")

    key.last_used_at = datetime.now(timezone.utc)
    db.add(key)
    request.state.api_key_id = key.id
    return ApiContext(org=org, env=env, key=key)
