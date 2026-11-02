"""Continue a liveness check on another device (QR code / link).

The signed-in user (e.g. on a laptop) asks for a handoff. They get:
  - a link with a random token, shown as a QR code, to open on a phone — no login there;
  - a handoff id the laptop polls to see when the phone has finished.

The link is single-use and short-lived:
  - valid for HANDOFF_TTL (10 minutes); after that it is `expired`;
  - once a check completes through it (passed), it is `completed` and can't start again;
  - failed attempts can be retried on the phone until it expires.

Only a SHA-256 of the token is kept. Like liveness sessions, handoffs live in
memory (single uvicorn worker).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException, status

from app.config import get_settings
from app.core.crypto import sha256_hex

HANDOFF_TTL_SECS = 10 * 60
_MAX_HANDOFFS = 200

HandoffStatus = Literal["pending", "in_progress", "completed", "expired", "cancelled"]


@dataclass
class Handoff:
    id: str
    token_hash: str
    user_id: str
    purpose: str            # enrol | verify
    consent: bool
    expires_at: float       # unix seconds
    status: HandoffStatus = "pending"
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)

    def refresh_expiry(self) -> None:
        if self.status in ("pending", "in_progress") and time.time() > self.expires_at:
            self.status = "expired"


_by_id: dict[str, Handoff] = {}
_by_token: dict[str, Handoff] = {}


def sweep() -> None:
    cutoff = time.time() - HANDOFF_TTL_SECS     # keep finished ones briefly so the laptop can read the result
    for hid in [h for h, v in _by_id.items() if v.expires_at < cutoff]:
        handoff = _by_id.pop(hid)
        _by_token.pop(handoff.token_hash, None)


def create(user_id: str, purpose: str, consent: bool) -> tuple[Handoff, str]:
    """Returns (handoff, link). Any earlier open handoff of this user is cancelled."""
    sweep()
    for h in _by_id.values():
        if h.user_id == user_id and h.status in ("pending", "in_progress"):
            h.status = "cancelled"
    if len(_by_id) >= _MAX_HANDOFFS:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Too many open handoffs — try again shortly")
    token = secrets.token_urlsafe(32)
    handoff = Handoff(
        id=secrets.token_hex(16),
        token_hash=sha256_hex(token),
        user_id=user_id,
        purpose=purpose,
        consent=consent,
        expires_at=time.time() + HANDOFF_TTL_SECS,
    )
    _by_id[handoff.id] = handoff
    _by_token[handoff.token_hash] = handoff
    return handoff, f"{get_settings().PUBLIC_APP_URL.rstrip('/')}/liveness/{token}"


def get_for_user(handoff_id: str, user_id: str) -> Handoff:
    handoff = _by_id.get(handoff_id)
    if handoff is None or handoff.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Handoff not found")
    handoff.refresh_expiry()
    return handoff


def get_by_token(token: str) -> Handoff:
    handoff = _by_token.get(sha256_hex(token))
    if handoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid")
    handoff.refresh_expiry()
    return handoff


def require_usable(handoff: Handoff) -> None:
    if handoff.status == "expired":
        raise HTTPException(status.HTTP_410_GONE, "This link has expired — start again on your other device")
    if handoff.status == "completed":
        raise HTTPException(status.HTTP_410_GONE, "This link has already been used")
    if handoff.status == "cancelled":
        raise HTTPException(status.HTTP_410_GONE, "This link was cancelled — start again on your other device")


def public_view(handoff: Handoff) -> dict[str, Any]:
    return {
        "status": handoff.status,
        "purpose": handoff.purpose,
        "expires_at": int(handoff.expires_at),
        "seconds_left": max(0, int(handoff.expires_at - time.time())),
        "result": handoff.result,
    }
