"""PKCE (RFC 7636, S256) and random state/nonce — for servers that start the sign-in themselves."""

from __future__ import annotations

import base64
import hashlib
import secrets


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def create_pkce() -> dict[str, str]:
    """{"code_verifier", "code_challenge", "state", "nonce"} — keep the verifier, state and nonce server-side."""
    verifier = _b64url(secrets.token_bytes(48))
    return {
        "code_verifier": verifier,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "state": _b64url(secrets.token_bytes(16)),
        "nonce": _b64url(secrets.token_bytes(16)),
    }
