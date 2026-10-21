"""Liveness challenge router — /api/v1/auth/me/liveness/*

Three-step active liveness flow:

  1. POST /start
       → issues a random set of 3 challenges and returns a session_id
       → the frontend does NOT know the challenges until this call

  2. POST /verify
       → accepts { session_id, challenge, frame } (frame = base64 JPEG/PNG)
       → runs OpenCV face detection to verify the user performed the challenge
       → marks the challenge as completed in the session
       → can be called once per challenge (retries on failure are allowed until
         the session expires)

  3. POST /complete
       → validates all 3 challenges are completed
       → saves the selfie frame as uploads/liveness/{user_id}.jpg
       → flips credential.claims.identity_verified = True
       → sets user.liveness_selfie_url
       → deletes the session
       → single atomic commit

Sessions expire after 10 minutes.  A user can only have one active session at a
time — starting a new one while one is active replaces the old one.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.dependencies import get_current_user
from app.models import Credential, LivenessSession, User
from app.services import liveness_service
from app.services.liveness_service import (
    ALL_CHALLENGES,
    CHALLENGE_INSTRUCTIONS,
    ChallengeType,
    check_challenge,
    pick_challenges,
    _decode_frame,
    _detect_largest_face,
)

router = APIRouter(prefix="/auth/me/liveness", tags=["liveness"])

_SESSION_TTL_MINUTES = 10
_CHALLENGES_PER_SESSION = 3
_UPLOAD_DIR = Path("uploads/liveness")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Request / response schemas (local — only used here)
# ---------------------------------------------------------------------------

class StartResponse(BaseModel):
    session_id: str
    challenges: list[str]          # ordered list, e.g. ["look_left", "open_mouth", "look_right"]
    instructions: list[str]        # human-readable, one per challenge
    expires_at: datetime


class PingRequest(BaseModel):
    frame: str                           # base64-encoded JPEG or PNG
    challenge: str | None = None         # current challenge name — triggers verifier if set


class PingResponse(BaseModel):
    face_detected: bool
    # When a challenge is active, also run it and report the result
    challenge_passed: bool | None   # None when no challenge supplied
    cx: float | None                # face centre x (0–1) for debug
    cy: float | None                # face centre y (0–1) for debug


class VerifyRequest(BaseModel):
    session_id: str
    challenge: str                  # must be one of ALL_CHALLENGES
    frame: str                      # base64-encoded JPEG or PNG


class VerifyResponse(BaseModel):
    passed: bool
    message: str
    completed: list[str]            # challenges completed so far this session
    remaining: list[str]            # challenges still to be done


class CompleteRequest(BaseModel):
    session_id: str
    # The final selfie frame (base64) — used as the stored liveness selfie
    frame: str


class CompleteResponse(BaseModel):
    passed: bool
    selfie_url: str | None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_active_session(session: LivenessSession | None) -> LivenessSession:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liveness session not found — call /start first",
        )
    if session.expires_at.replace(tzinfo=timezone.utc) < _now():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Liveness session has expired — call /start to begin a new one",
        )
    return session


def _decode_frame(frame_b64: str) -> bytes:
    try:
        return base64.b64decode(frame_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="frame must be a valid base64-encoded image",
        )


async def _get_session(session_id: str, user: User, db: AsyncSession) -> LivenessSession | None:
    result = await db.exec(
        select(LivenessSession).where(
            LivenessSession.id == session_id,
            LivenessSession.user_id == user.id,
        )
    )
    return result.first()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/ping", response_model=PingResponse)
async def ping_frame(
    body: PingRequest,
    current_user: User = Depends(get_current_user),
) -> PingResponse:
    """Lightweight face-detection probe — no DB writes.

    Called by the test page every ~700ms to drive the live oval feedback.
    When body.challenge is set it also runs the challenge verifier so the
    frontend can auto-capture the moment the condition is satisfied.
    """
    try:
        image_bytes = base64.b64decode(body.frame)
        frame = _decode_frame(image_bytes)
        face  = _detect_largest_face(frame)
    except Exception:
        return PingResponse(face_detected=False, challenge_passed=None, cx=None, cy=None)

    if face is None:
        return PingResponse(face_detected=False, challenge_passed=None, cx=None, cy=None)

    # Optionally run the current challenge verifier
    challenge_passed: bool | None = None
    if body.challenge and body.challenge in ALL_CHALLENGES:
        try:
            passed, _ = check_challenge(body.challenge, image_bytes)  # type: ignore[arg-type]
            challenge_passed = passed
        except Exception:
            challenge_passed = False

    return PingResponse(
        face_detected=True,
        challenge_passed=challenge_passed,
        cx=round(face.cx, 3),
        cy=round(face.cy, 3),
    )


@router.post("/start", response_model=StartResponse, status_code=status.HTTP_201_CREATED)
async def start_liveness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartResponse:
    """Create a new liveness session with a fresh random challenge set.

    Any existing active session for this user is deleted first — only one
    session per user at a time.
    """
    # Delete any existing session for this user
    existing = await db.exec(
        select(LivenessSession).where(LivenessSession.user_id == current_user.id)
    )
    for old in existing.all():
        await db.delete(old)

    challenges: list[ChallengeType] = pick_challenges(_CHALLENGES_PER_SESSION)
    expires_at = _now() + timedelta(minutes=_SESSION_TTL_MINUTES)

    session = LivenessSession(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        challenges=list(challenges),
        completed=[],
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    print(
        f"[liveness] session {session.id} started for user {current_user.id} "
        f"challenges={challenges}",
        flush=True,
    )

    return StartResponse(
        session_id=session.id,
        challenges=list(challenges),
        instructions=[CHALLENGE_INSTRUCTIONS[c] for c in challenges],
        expires_at=expires_at,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_challenge(
    body: VerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """Submit a single challenge frame for verification.

    The frontend should call this once per challenge, in the order returned
    by /start.  Retries on failure are allowed until the session expires.
    """
    raw_session = await _get_session(body.session_id, current_user, db)
    session = _require_active_session(raw_session)

    # Validate the challenge belongs to this session
    if body.challenge not in session.challenges:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Challenge '{body.challenge}' is not part of this session",
        )

    # Already completed — idempotent success
    if body.challenge in session.completed:
        remaining = [c for c in session.challenges if c not in session.completed]
        return VerifyResponse(
            passed=True,
            message="Challenge already completed",
            completed=list(session.completed),  # type: ignore[arg-type]
            remaining=remaining,
        )

    # Validate challenge name
    if body.challenge not in ALL_CHALLENGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown challenge '{body.challenge}'",
        )

    image_bytes = _decode_frame(body.frame)

    try:
        passed, reason = check_challenge(body.challenge, image_bytes)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if passed:
        # Append to completed list (JSON column — replace with new list)
        updated_completed = list(session.completed) + [body.challenge]  # type: ignore[operator]
        session.completed = updated_completed  # type: ignore[assignment]
        db.add(session)
        await db.commit()
        await db.refresh(session)

    completed_now: list[str] = list(session.completed)  # type: ignore[arg-type]
    remaining = [c for c in session.challenges if c not in completed_now]  # type: ignore[operator]

    print(
        f"[liveness] verify session={session.id} challenge={body.challenge} "
        f"passed={passed} completed={completed_now}",
        flush=True,
    )

    return VerifyResponse(
        passed=passed,
        message=reason,
        completed=completed_now,
        remaining=remaining,
    )


@router.post("/complete", response_model=CompleteResponse)
async def complete_liveness(
    body: CompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompleteResponse:
    """Finalise the liveness session.

    Requirements:
      - All 3 challenges must be in session.completed
      - The final selfie frame is saved to uploads/liveness/{user_id}.jpg
      - credential.claims.identity_verified is set to True
      - user.liveness_selfie_url is updated
      - The session is deleted
      - Everything committed in a single atomic write
    """
    raw_session = await _get_session(body.session_id, current_user, db)
    session = _require_active_session(raw_session)

    completed: list[str] = list(session.completed)  # type: ignore[arg-type]
    challenges: list[str] = list(session.challenges)  # type: ignore[arg-type]
    missing = [c for c in challenges if c not in completed]

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not all challenges completed — still pending: {missing}",
        )

    # Save selfie frame
    image_bytes = _decode_frame(body.frame)
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    selfie_path = _UPLOAD_DIR / f"{current_user.id}.jpg"

    try:
        with open(selfie_path, "wb") as f:
            f.write(image_bytes)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save selfie — please try again",
        ) from exc

    selfie_url = str(selfie_path)

    # Update user
    current_user.liveness_selfie_url = selfie_url
    db.add(current_user)

    # Update credential
    cred: Credential | None = current_user.credential
    if cred is not None:
        updated_claims: Any = dict(cred.claims)  # type: ignore[arg-type]
        updated_claims["identity_verified"] = True
        cred.claims = updated_claims
        cred.updated_at = _now()
        db.add(cred)

    # Delete session
    await db.delete(session)

    # Single atomic commit
    await db.commit()

    print(
        f"[liveness] COMPLETE user={current_user.id} selfie={selfie_url}",
        flush=True,
    )

    return CompleteResponse(
        passed=True,
        selfie_url=selfie_url,
        message="Liveness verification passed — identity confirmed",
    )
