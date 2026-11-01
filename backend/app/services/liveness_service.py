"""Liveness engine service — wraps the `faceliveness` SDK.

The engine runs **on the server**, never on the user's device (a result computed
on the device can be faked).  The flow mirrors face-liveness/demo/server.mjs:

  1. start_session()  → the server issues a signed ticket (it fixes the challenges)
                        and builds an Engine from it.  The ticket never leaves
                        the server; the client only gets the nonce + challenges.
  2. process_frame()  → the client streams JPEG frames; each is decoded and fed to
                        the engine with the SERVER clock as timestamp.
  3. once done        → the engine signs a receipt (Ed25519 JWT) recording the
                        outcome and the SHA-256 of the captured face PNG.

Sessions live in memory, keyed by nonce.  This requires a single uvicorn worker
(the Dockerfile already runs --workers 1).
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import cv2
import faceliveness
import numpy as np
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.config import get_settings

Purpose = Literal["enrol", "verify"]

# Blinks are unreliable with glasses (see face-liveness docs/threat-model.md),
# so challenges are drawn from head turns and mouth only.
_CHALLENGE_POOL = ["turn_left", "turn_right", "open_mouth"]

_TICKET_TTL_SECS = 120
_SESSION_TTL_SECS = 180
_MAX_SESSIONS = 50
_MAX_FRAME_SIDE = 1280
_MAX_FRAME_BYTES = 2 * 1024 * 1024

CHALLENGE_PROMPTS: dict[str, str] = {
    "blink": "Blink",
    "turn_left": "Turn your head to your left",
    "turn_right": "Turn your head to your right",
    "open_mouth": "Open your mouth wide",
}


# ---------------------------------------------------------------------------
# Signing key
# ---------------------------------------------------------------------------

@lru_cache
def get_signing_key() -> faceliveness.SigningKey:
    """Load LIVENESS_SIGNING_KEY (64 hex chars); generate an ephemeral one in dev."""
    settings = get_settings()
    if settings.LIVENESS_SIGNING_KEY:
        return faceliveness.SigningKey.from_bytes(bytes.fromhex(settings.LIVENESS_SIGNING_KEY))
    if settings.ENV == "production":
        raise RuntimeError("LIVENESS_SIGNING_KEY must be set in production")
    print(
        "[liveness] WARNING: LIVENESS_SIGNING_KEY not set — using an ephemeral key "
        "(receipts will not survive a restart)",
        flush=True,
    )
    return faceliveness.SigningKey.generate()


def get_public_key() -> bytes:
    return get_signing_key().public_key


# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

@dataclass
class FinalResult:
    passed: bool
    fail_reason: str | None
    receipt: str | None
    face_png: bytes | None


@dataclass
class LivenessRun:
    nonce: str
    user_id: str
    purpose: Purpose
    challenges: list[str]
    engine: faceliveness.Engine
    started: float = field(default_factory=time.monotonic)
    expires_at: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    final: FinalResult | None = None
    last: dict[str, object] = field(default_factory=dict)


_sessions: dict[str, LivenessRun] = {}


def sweep_expired() -> int:
    """Drop sessions older than the session TTL. Returns the number removed."""
    cutoff = time.monotonic() - _SESSION_TTL_SECS
    stale = [n for n, s in _sessions.items() if s.started < cutoff]
    for nonce in stale:
        del _sessions[nonce]
    return len(stale)


def start_session(user_id: str, purpose: Purpose) -> LivenessRun:
    """Issue a ticket and build an engine. Replaces any session the user already has."""
    sweep_expired()
    for nonce in [n for n, s in _sessions.items() if s.user_id == user_id]:
        del _sessions[nonce]
    if len(_sessions) >= _MAX_SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Too many liveness checks in progress — try again shortly",
        )

    settings = get_settings()
    key = get_signing_key()
    count = max(1, min(settings.LIVENESS_CHALLENGE_COUNT, len(_CHALLENGE_POOL)))
    challenges = random.SystemRandom().sample(_CHALLENGE_POOL, k=count)

    ticket = key.issue_ticket(challenges, ttl_secs=_TICKET_TTL_SECS)
    parsed = faceliveness.verify_ticket(ticket, key.public_key)
    engine = faceliveness.Engine.from_ticket(ticket, key.public_key)

    run = LivenessRun(
        nonce=parsed.nonce,
        user_id=user_id,
        purpose=purpose,
        challenges=list(parsed.challenges),
        engine=engine,
        expires_at=parsed.expires_at,
    )
    _sessions[run.nonce] = run
    return run


def get_session(nonce: str, user_id: str) -> LivenessRun:
    run = _sessions.get(nonce)
    if run is None or run.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liveness session not found or expired — start a new check",
        )
    return run


def end_session(nonce: str) -> None:
    _sessions.pop(nonce, None)


# ---------------------------------------------------------------------------
# Frame processing
# ---------------------------------------------------------------------------

def _decode_jpeg(data: bytes) -> np.ndarray:
    if not data or len(data) > _MAX_FRAME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Frame missing or too large",
        )
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Frame is not a valid image",
        )
    h, w = frame.shape[:2]
    if max(h, w) > _MAX_FRAME_SIDE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Frame larger than {_MAX_FRAME_SIDE}px",
        )
    return frame


def _run_engine(run: LivenessRun, frame: np.ndarray, timestamp_ms: int) -> dict[str, object]:
    result = run.engine.process(frame, timestamp_ms, format="bgr")
    state: dict[str, object] = {
        "status": result.status,
        "done": result.done,
        "current_challenge": result.current_challenge,
        "remaining": result.remaining,
        "fail_reason": result.fail_reason,
        "face_count": result.face_count,
    }
    if result.done:
        capture = run.engine.capture
        receipt: str | None = None
        try:
            receipt = run.engine.receipt(get_signing_key())
        except ValueError as exc:   # e.g. the ticket expired before the session ended
            print(f"[liveness] receipt not issued for {run.nonce}: {exc}", flush=True)
        passed = result.status == "passed" and receipt is not None
        run.final = FinalResult(
            passed=passed,
            fail_reason=None if passed else (result.fail_reason or "timeout"),
            receipt=receipt,
            face_png=capture.png if capture is not None else None,
        )
        state["status"] = "passed" if run.final.passed else "failed"
        state["fail_reason"] = run.final.fail_reason
    return state


async def process_frame(run: LivenessRun, data: bytes) -> dict[str, object]:
    """Feed one JPEG frame to the session's engine (one frame at a time per session)."""
    if run.final is not None:
        return run.last
    if run.lock.locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Previous frame still processing",
        )
    async with run.lock:
        frame = _decode_jpeg(data)
        # Server clock, never the client's — a client can't fake timing this way.
        timestamp_ms = int((time.monotonic() - run.started) * 1000)
        run.last = await run_in_threadpool(_run_engine, run, frame, timestamp_ms)
        return run.last
