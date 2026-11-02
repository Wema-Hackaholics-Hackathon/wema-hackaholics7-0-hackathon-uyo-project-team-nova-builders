"""Public liveness endpoints — /api/v1/liveness/*  (no login)

Frames
  POST /sessions/{nonce}/frame?w=&h=    raw RGBA body (canvas ImageData), one at a time
       The session's unguessable nonce is the credential — exactly like
       face-liveness/demo/server.mjs — so a frame costs no login lookup and no
       database query. The server's clock times the session; the server alone
       decides pass/fail and signs the receipt.

Continue on another device (the phone side of a handoff, see services/liveness_handoff.py)
  GET  /handoff/{token}                 who/what this link is for, status, time left
  POST /handoff/{token}/start           start a check for the account that created the link
  POST /handoff/{token}/complete        {session_id} → same result as the first-party flow
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.models import User
from app.routers.liveness import CompleteResponse, StartResponse, finish_run
from app.services import liveness_handoff as handoffs
from app.services import liveness_service as ls
from app.utils.limiter import limiter

router = APIRouter(prefix="/liveness", tags=["liveness-public"])


class FrameResponse(BaseModel):
    status: str                     # in_progress | passed | failed
    done: bool
    current_challenge: str | None
    remaining: int
    fail_reason: str | None
    face_count: int
    actions: list[str] = []


class CompleteBody(BaseModel):
    session_id: str


@router.post("/sessions/{nonce}/frame", response_model=FrameResponse)
async def submit_frame(
    nonce: str,
    request: Request,
    w: Annotated[int, Query(ge=16, le=1280)],
    h: Annotated[int, Query(ge=16, le=1280)],
) -> FrameResponse:
    run = ls.get_session_by_nonce(nonce)
    state = await ls.process_frame(run, await request.body(), w, h)
    return FrameResponse.model_validate(state)


# ── Handoff (phone side) ────────────────────────────────────────────────────

async def _handoff_user(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid")
    return user


@router.get("/handoff/{token}")
async def handoff_info(token: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    handoff = handoffs.get_by_token(token)
    user = await _handoff_user(db, handoff.user_id)
    return {
        **handoffs.public_view(handoff),
        # enough for the person to confirm it's their own check, nothing more
        "display_name": f"{user.first_name} {user.last_name[:1]}.",
    }


@router.post("/handoff/{token}/start", response_model=StartResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def handoff_start(request: Request, token: str) -> StartResponse:  # request: required by slowapi
    handoff = handoffs.get_by_token(token)
    handoffs.require_usable(handoff)
    handoff.status = "in_progress"
    run = ls.start_session(handoff.user_id, handoff.purpose)   # same owner key as the first-party flow
    return StartResponse(
        session_id=run.nonce,
        purpose=run.purpose,
        challenges=run.challenges,
        instructions=[ls.CHALLENGE_PROMPTS.get(c, c) for c in run.challenges],
        expires_at=datetime.fromtimestamp(run.expires_at, tz=timezone.utc),
    )


@router.post("/handoff/{token}/complete", response_model=CompleteResponse)
async def handoff_complete(
    token: str,
    body: CompleteBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompleteResponse:
    handoff = handoffs.get_by_token(token)
    handoffs.require_usable(handoff)
    user = await _handoff_user(db, handoff.user_id)
    result = await finish_run(db, user, ls.get_session(body.session_id, user.id))
    handoff.result = result.model_dump()
    if result.passed:
        handoff.status = "completed"      # single use: a successful check closes the link
    return result
