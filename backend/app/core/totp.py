"""Time-based one-time codes (RFC 6238: SHA-1, 6 digits, 30 s) for console two-step sign-in.

Works with Google Authenticator, Microsoft Authenticator, 1Password, Authy, etc.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10 ** DIGITS:0{DIGITS}d}"


def code_at(secret: str, when: float | None = None) -> str:
    return _code(secret, int((when if when is not None else time.time()) // STEP))


def verify(secret: str, code: str, last_step: int | None = None, window: int = 1) -> int | None:
    """The matching step (±window, for clock drift), or None. A step at or before `last_step` is refused (no replay)."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = int(time.time() // STEP)
    for step in range(now - window, now + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "FOID Console") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}")
