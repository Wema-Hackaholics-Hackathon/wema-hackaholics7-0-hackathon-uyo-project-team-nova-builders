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


# ---------------------------------------------------------------------------
# Business console access tokens — a different token type from user tokens,
# so a user-app token never works on the console and vice versa.
# ---------------------------------------------------------------------------

def create_console_access_token(console_user_id: str, kind: str = "console", minutes: int | None = None) -> str:
    """kind="console" → normal session; kind="console_mfa" → 5-minute ticket between password and 2FA code."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": console_user_id, "exp": expire, "type": kind}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_console_access_token(token: str, kind: str = "console") -> str:
    """Return the console user id. Raises ``jose.JWTError`` for any other token type."""
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != kind:
        raise JWTError("wrong token type")
    sub: object = payload.get("sub")
    if not isinstance(sub, str):
        raise JWTError("missing sub claim")
    return sub


# ---------------------------------------------------------------------------
# Short-lived single-purpose tickets (user 2FA step, passkey challenges).
# `kind` is checked on decode, so a ticket is never accepted as a session token.
# ---------------------------------------------------------------------------

def create_ticket(sub: str, kind: str, minutes: int = 5) -> str:
    return create_console_access_token(sub, kind, minutes=minutes)


def decode_ticket(token: str, kind: str) -> str:
    """The ticket's subject. Raises ``jose.JWTError`` if expired, tampered or of another kind."""
    return decode_console_access_token(token, kind)
