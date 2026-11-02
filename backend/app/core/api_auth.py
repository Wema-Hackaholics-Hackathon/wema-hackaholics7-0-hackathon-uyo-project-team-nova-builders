"""Authentication for the public Open API (/api/open/v1/*).

    Authorization: Bearer FOID_TEST_...   (sandbox: mock providers, never billed)
    Authorization: Bearer FOID_LIVE_...   (live: only after FOID approves the business — KYB)

The raw key is shown ONCE, in the response that creates it. FOID keeps only its
SHA-256 hash (for lookup) and a display hint like FOID_LIVE_28…29 — a leaked
database can't be used to call the API, and nobody (FOID staff included) can
read a key back. Lost key → create a new one and revoke the old one.

Keys from before the FOID_ format (sk_test_/sk_live_) keep working until revoked.
"""

from __future__ import annotations

import ipaddress
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.crypto import sha256_hex
from app.models import ApiKey, Organisation

KEY_PREFIX = {"test": "FOID_TEST_", "live": "FOID_LIVE_"}
_LEGACY_PREFIX = {"test": "sk_test_", "live": "sk_live_"}
_ALPHABET = string.ascii_letters + string.digits   # no "_" or "-", so the hint is unambiguous
_SECRET_LEN = 40                                   # ≈ 238 bits


@dataclass
class ApiContext:
    org: Organisation
    env: str
    key: ApiKey


def key_hint(raw: str) -> str:
    """FOID_LIVE_28…29 — enough to tell keys apart, useless to an attacker."""
    prefix = next(p for p in (*KEY_PREFIX.values(), *_LEGACY_PREFIX.values()) if raw.startswith(p))
    secret = raw[len(prefix):]
    return f"{prefix}{secret[:2]}…{secret[-2:]}"


def generate_api_key(env: str) -> tuple[str, str, str]:
    """Return (raw_key, display_hint, key_hash). Only the hint and the hash are stored."""
    raw = KEY_PREFIX[env] + "".join(secrets.choice(_ALPHABET) for _ in range(_SECRET_LEN))
    return raw, key_hint(raw), sha256_hex(raw)


def key_env(raw: str) -> str | None:
    for env in ("live", "test"):
        if raw.startswith(KEY_PREFIX[env]) or raw.startswith(_LEGACY_PREFIX[env]):
            return env
    return None


def ip_allowed(ip: str | None, allowlist: list[str]) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(net, strict=False) for net in allowlist)


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
        raise ApiError(401, "missing_api_key", "Send your secret key as 'Authorization: Bearer FOID_TEST_...'")
    raw = auth[7:].strip()
    env = key_env(raw)
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
    if env == "live" and org.ip_allowlist and not ip_allowed(request.client.host if request.client else None, org.ip_allowlist):
        # client address as uvicorn sees it — behind a proxy run uvicorn with --proxy-headers
        raise ApiError(403, "ip_not_allowed", "Live keys for this business only work from its allow-listed IP addresses")

    key.last_used_at = datetime.now(timezone.utc)
    db.add(key)
    request.state.api_key_id = key.id
    request.state.api_org_id = org.id
    request.state.api_env = env
    request.state.api_key_hint = key.prefix
    return ApiContext(org=org, env=env, key=key)
