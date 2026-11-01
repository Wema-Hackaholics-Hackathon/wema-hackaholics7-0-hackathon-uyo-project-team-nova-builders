"""Liveness + face matching router — /api/v1/auth/me/liveness/*

Built on the faceliveness SDK (engine runs on this server) and SFace:

  1. POST /start                  {purpose: "enrol"|"verify", consent}
       → server issues a signed ticket (kept server-side) and returns the
         nonce + challenges the user must perform
  2. POST /{nonce}/frame          body: image/jpeg
       → one frame at a time; returns the current challenge / outcome
  3. POST /{nonce}/complete
       enrol  → verify_face_record + replay check → embed → store encrypted
                template → identity_verified=True (+ notification)
       verify → verify_face_record + replay check → embed → 1:1 match against
                the enrolled template → {matched, score}

  GET    /status      → { enrolled, verified_at, quality }
  GET    /face        → the user's own stored face-record PNG
  DELETE /enrolment   → delete template + face (right to erasure)

Sessions are in-memory: run a single uvicorn worker.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_db
from app.core.dependencies import get_current_user, require_verified_email
from app.models import Credential, FaceEnrolment, LivenessAttempt, Notification, User
from app.services import face_match_service as fm
from app.services import liveness_service as ls
from app.utils.limiter import limiter

router = APIRouter(prefix="/auth/me/liveness", tags=["liveness"])

_FACE_URL = "/api/v1/auth/me/liveness/face"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Schemas (local — only used here)
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    purpose: Literal["enrol", "verify"] = "enrol"
    consent: bool = False


class StartResponse(BaseModel):
    session_id: str
    purpose: str
    challenges: list[str]
    instructions: list[str]
    expires_at: datetime


class FrameResponse(BaseModel):
    status: str                     # in_progress | passed | failed
    done: bool
    current_challenge: str | None
    remaining: int
    fail_reason: str | None
    face_count: int


class CompleteResponse(BaseModel):
    purpose: str
    passed: bool
    enrolled: bool = False
    matched: bool | None = None
    score: float | None = None
    face_quality: float | None = None
    message: str


class StatusResponse(BaseModel):
    enrolled: bool
    verified_at: datetime | None
    face_quality: float | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_enrolment(user_id: str, db: AsyncSession) -> FaceEnrolment | None:
    result = await db.exec(select(FaceEnrolment).where(FaceEnrolment.user_id == user_id))
    return result.first()


async def _set_identity_claim(user: User, value: bool, db: AsyncSession) -> None:
    """Flip identity_verified and record a notification when it changes."""
    result = await db.exec(select(Credential).where(Credential.user_id == user.id))
    cred = result.first()
    if cred is None or bool(cred.claims.get("identity_verified")) == value:  # type: ignore[union-attr]
        return
    cred.claims = {**cred.claims, "identity_verified": value}  # type: ignore[assignment]
    cred.updated_at = _now()
    db.add(cred)
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="Identity verified" if value else "Identity verification removed",
        change=f"identity_verified: {not value} → {value}",
        reason=(
            "You passed a liveness check and your face was enrolled."
            if value else "Your enrolled face data was deleted."
        ),
        action=(
            "No action needed." if value
            else "Complete a new liveness check to restore your identity verification."
        ),
    ))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StartResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def start_liveness(
    request: Request,  # required by slowapi
    body: StartRequest,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StartResponse:
    """Start a liveness session. Enrolment needs explicit biometric consent."""
    if body.purpose == "enrol" and not body.consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent to process your face data is required",
        )
    if body.purpose == "verify" and await _get_enrolment(current_user.id, db) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No face enrolled yet — complete identity liveness first",
        )

    run = ls.start_session(current_user.id, body.purpose)
    print(
        f"[liveness] start user={current_user.id} purpose={body.purpose} "
        f"nonce={run.nonce} challenges={run.challenges}",
        flush=True,
    )
    return StartResponse(
        session_id=run.nonce,
        purpose=run.purpose,
        challenges=run.challenges,
        instructions=[ls.CHALLENGE_PROMPTS.get(c, c) for c in run.challenges],
        expires_at=datetime.fromtimestamp(run.expires_at, tz=timezone.utc),
    )


@router.post("/{session_id}/frame", response_model=FrameResponse)
async def submit_frame(
    session_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> FrameResponse:
    """Process one JPEG frame (raw request body)."""
    run = ls.get_session(session_id, current_user.id)
    state = await ls.process_frame(run, await request.body())
    return FrameResponse.model_validate(state)


@router.post("/{session_id}/complete", response_model=CompleteResponse)
async def complete_liveness(
    session_id: str,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompleteResponse:
    """Finalise a finished session: enrol the face or match it 1:1."""
    run = ls.get_session(session_id, current_user.id)
    final = run.final
    if final is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Liveness session is not finished yet",
        )
    ls.end_session(session_id)

    if not final.passed or final.receipt is None or final.face_png is None:
        db.add(LivenessAttempt(
            user_id=current_user.id, nonce=run.nonce, purpose=run.purpose,
            passed=False, fail_reason=final.fail_reason,
        ))
        await db.commit()
        return CompleteResponse(
            purpose=run.purpose,
            passed=False,
            message=f"Liveness check failed: {final.fail_reason or 'no face captured'}",
        )

    accepted = await fm.accept_face_record(
        db=db,
        user_id=current_user.id,
        purpose=run.purpose,
        receipt=final.receipt,
        face_png=final.face_png,
    )
    try:
        embedding = await run_in_threadpool(fm.embed, accepted.face_png)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read the captured face: {exc}",
        ) from exc

    if run.purpose == "enrol":
        enrolment = await _get_enrolment(current_user.id, db)
        if enrolment is None:
            enrolment = FaceEnrolment(
                user_id=current_user.id,
                template_enc=b"",
                face_png=b"",
                face_sha256="",
                receipt="",
                face_quality=0.0,
                model=fm.MODEL_NAME,
                consent_at=_now(),
            )
        enrolment.template_enc = fm.encrypt_template(embedding)
        enrolment.face_png = accepted.face_png
        enrolment.face_sha256 = accepted.face_sha256
        enrolment.receipt = final.receipt
        enrolment.face_quality = accepted.quality
        enrolment.model = fm.MODEL_NAME
        enrolment.consent_at = _now()
        enrolment.updated_at = _now()
        db.add(enrolment)

        current_user.liveness_selfie_url = _FACE_URL
        current_user.liveness_verified_at = _now()
        db.add(current_user)
        await _set_identity_claim(current_user, True, db)

        db.add(LivenessAttempt(
            user_id=current_user.id, nonce=run.nonce, purpose="enrol", passed=True,
            face_quality=accepted.quality, real_score=accepted.real_score,
        ))
        await db.commit()
        print(f"[liveness] ENROLLED user={current_user.id} quality={accepted.quality:.2f}", flush=True)
        return CompleteResponse(
            purpose="enrol",
            passed=True,
            enrolled=True,
            face_quality=accepted.quality,
            message="Liveness passed — your face is enrolled and identity verified",
        )

    # purpose == "verify": 1:1 match against the enrolled template
    enrolment = await _get_enrolment(current_user.id, db)
    if enrolment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No face enrolled — complete identity liveness first",
        )
    score = fm.cosine(embedding, fm.decrypt_template(enrolment.template_enc))
    matched = fm.is_match(score)
    db.add(LivenessAttempt(
        user_id=current_user.id, nonce=run.nonce, purpose="verify", passed=True,
        face_quality=accepted.quality, real_score=accepted.real_score, match_score=score,
    ))
    await db.commit()
    print(f"[liveness] VERIFY user={current_user.id} score={score:.3f} matched={matched}", flush=True)
    return CompleteResponse(
        purpose="verify",
        passed=True,
        matched=matched,
        score=round(score, 4),
        face_quality=accepted.quality,
        message="Face matches your enrolled identity" if matched
        else "Face does not match your enrolled identity",
    )


@router.get("/status", response_model=StatusResponse)
async def liveness_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StatusResponse:
    enrolment = await _get_enrolment(current_user.id, db)
    return StatusResponse(
        enrolled=enrolment is not None,
        verified_at=current_user.liveness_verified_at,
        face_quality=enrolment.face_quality if enrolment else None,
    )


@router.get("/face")
async def get_face(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """The user's own enrolled face record (112x112 PNG)."""
    enrolment = await _get_enrolment(current_user.id, db)
    if enrolment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No face enrolled")
    return Response(
        content=enrolment.face_png,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/enrolment", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrolment(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete the user's face template and image, and reset identity_verified."""
    enrolment = await _get_enrolment(current_user.id, db)
    if enrolment is not None:
        await db.delete(enrolment)
    current_user.liveness_selfie_url = None
    current_user.liveness_verified_at = None
    db.add(current_user)
    await _set_identity_claim(current_user, False, db)
    await db.commit()
