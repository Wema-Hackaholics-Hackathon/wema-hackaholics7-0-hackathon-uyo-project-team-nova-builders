"""Password hashing and JWT token utilities.

Password hashing uses argon2-cffi (Argon2id).
Tokens use python-jose with HS256.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config import get_settings

_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return an Argon2id hash of *plain*."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*, False otherwise."""
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# Refresh-token raw value + hash helpers
# ---------------------------------------------------------------------------

def generate_refresh_token() -> str:
    """Return a cryptographically random 64-byte hex string."""
    return secrets.token_hex(64)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hex digest of *raw* — stored in DB, never the raw value."""
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    """Create a short-lived JWT access token for *user_id*."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str:
    """Decode *token* and return the user_id (sub claim).

    Raises ``jose.JWTError`` if the token is invalid or expired.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    token_type: object = payload.get("type")
    if token_type != "access":
        raise JWTError("wrong token type")
    sub: object = payload.get("sub")
    if not isinstance(sub, str):
        raise JWTError("missing sub claim")
    return sub


def create_refresh_token_expiry() -> datetime:
    """Return the expiry datetime for a new refresh token."""
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
