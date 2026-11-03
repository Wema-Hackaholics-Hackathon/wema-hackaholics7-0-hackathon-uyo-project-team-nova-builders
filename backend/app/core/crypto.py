"""Small crypto helpers shared by the business platform.

- encrypt_str / decrypt_str : Fernet for secrets that must be recovered later
                              (webhook signing secrets).
- pii_hash                  : keyed HMAC-SHA256 for NIN / BVN lookups. A plain
                              SHA-256 of an 11-digit number is brute-forceable
                              in minutes, so a server-side key is required.
- api key / token helpers   : random tokens, stored only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


def _derive(label: str) -> bytes:
    settings = get_settings()
    if settings.ENV == "production":
        raise RuntimeError(f"{label} must be set in production")
    return hashlib.sha256(f"{settings.SECRET_KEY}:{label}".encode()).digest()


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().DATA_ENCRYPTION_KEY
    if key:
        return Fernet(key.encode())
    return Fernet(base64.urlsafe_b64encode(_derive("DATA_ENCRYPTION_KEY")))


def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def encrypt_bytes(value: bytes) -> bytes:
    return _fernet().encrypt(value)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def decrypt_str(token: str, ttl: int | None = None) -> str:
    """`ttl` (seconds): reject tokens older than this (InvalidToken), using the time inside the token."""
    return _fernet().decrypt(token.encode(), ttl=ttl).decode()


@lru_cache
def _pii_key() -> bytes:
    key = get_settings().PII_HASH_KEY
    return key.encode() if key else _derive("PII_HASH_KEY")


def pii_hash(value: str) -> str:
    """Keyed hash of an identifier (NIN/BVN) so records can be matched without storing it."""
    return hmac.new(_pii_key(), value.strip().encode(), hashlib.sha256).hexdigest()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token(prefix: str, nbytes: int = 24) -> str:
    return f"{prefix}{secrets.token_urlsafe(nbytes)}"


def mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    return "*" * max(0, len(value) - keep) + value[-keep:]
