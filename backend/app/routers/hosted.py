"""Hosted verification flow — the FOID-branded page a business sends people to.

Mounted at /api/v1/hosted/sessions/{token}. The token is the `client_token` from
POST /api/open/v1/verifications (also the last segment of `hosted_url`). No FOID
login is needed — the person may not have a FOID account at all.

Order enforced by the server:
  GET  ""                     what to show: business branding, purpose, checks, progress
  POST /consent {accept}      must come first; creates the consent grant (or declines)
  POST /share-foid            optional, FOID Bearer: reuse what FOID already verified
  POST /nin | /nin-document | /bvn
  POST /liveness/start → frames to /api/v1/liveness/sessions/{id}/frame (no DB per frame) → /liveness/{id}/complete
  POST /finish                closes the verification, notifies the business, returns redirect
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.crypto import sha256_hex
from app.core.dependencies import get_current_user
from app.models import CheckResult, Credential, FaceEnrolment, Subject, SubjectFace, User, Verification
from app.services import checks_service as cs
from app.services import consent_service as consent
from app.services import face_match_service as fm
from app.services import liveness_service as ls
from app.services.subject_link_service import link, link_user_for_subject
from app.services.webhook_service import enqueue_event
from app.utils.limiter import limiter

router = APIRouter(prefix="/hosted/sessions/{token}", tags=["hosted-verification"])

Db = Annotated[AsyncSession, Depends(get_db)]


class ConsentBody(BaseModel):
    accept: bool


class NumberBody(BaseModel):
    number: str = Field(min_length=11, max_length=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load(db: AsyncSession, token: str) -> tuple[Verification, Subject]:
    v = (await db.exec(select(Verification).where(Verification.session_token_hash == sha256_hex(token)))).first()
    if v is None:
        raise ApiError(404, "session_not_found", "This verification link is invalid")
    subject = await db.get(Subject, v.subject_id)
    if subject is None:
        raise ApiError(410, "session_not_found", "This verification is no longer available")
    return v, subject


async def _load_open(db: AsyncSession, token: str, *, need_consent: bool = True) -> tuple[Verification, Subject]:
    v, subject = await _load(db, token)
    cs.ensure_open(v)
    if need_consent and v.status == "pending":
        raise ApiError(409, "consent_required", "Accept the consent screen first")
    return v, subject


async def _step_guard(db: AsyncSession, v: Verification, check: str) -> None:
    if check not in v.checks:
        raise ApiError(400, "check_not_requested", f"This verification does not include '{check}'")
    latest = (await cs.latest_results(db, v.id)).get(check)
    if latest is not None and latest.status == "passed":
        raise ApiError(409, "check_already_passed", f"'{check}' is already complete")
    if await cs.attempts(db, v.id, check) >= cs.MAX_ATTEMPTS_PER_CHECK:
        raise ApiError(429, "too_many_attempts", f"No attempts left for '{check}'")


def _person_view(r: CheckResult) -> dict[str, Any]:
    """What the person sees about their own step — status only, no registry data."""
    return {"type": r.type, "status": r.status, "reasons": r.reasons}


async def _state(db: AsyncSession, v: Verification, subject: Subject) -> dict[str, Any]:
    latest = await cs.latest_results(db, v.id)
    steps = []
    for c in v.checks:
        r = latest.get(c)
        used = await cs.attempts(db, v.id, c)
        steps.append({
            "type": c,
            "status": r.status if r else "pending",
            "reasons": r.reasons if r else [],
            "attempts_left": max(0, cs.MAX_ATTEMPTS_PER_CHECK - used),
            "source": (r.data.get("source") if r else None) or "this_session",
        })
    return {
        "id": v.id,
        "env": v.env,
        "business": await cs.org_branding(db, v.org_id),
        "purpose": v.purpose,
        "scopes": [{"scope": s, "description": consent.SCOPES[s]} for s in v.scopes],
        "status": v.status,
        "outcome": v.outcome,
        "consent_given": v.status != "pending",
        "reused_foid_credential": v.reused_foid_credential,
        "steps": steps,
        "person": {"first_name": subject.first_name},
        "expires_at": cs.iso(v.expires_at),
    }


def _redirect(v: Verification) -> str | None:
    if not v.return_url:
        return None
    sep = "&" if "?" in v.return_url else "?"
    return v.return_url + sep + urlencode({"verification_id": v.id, "status": v.status, "outcome": v.outcome or ""})


# ---------------------------------------------------------------------------
# Session + consent
# ---------------------------------------------------------------------------

@router.get("")
async def get_session(token: str, db: Db) -> dict[str, Any]:
    v, subject = await _load(db, token)
    out = await _state(db, v, subject)
    if v.status in ("completed", "cancelled"):
        out["redirect_url"] = _redirect(v)
    return out


@router.post("/consent")
@limiter.limit("20/minute")
async def give_consent(request: Request, token: str, body: ConsentBody, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token, need_consent=False)
    if v.status != "pending":
        raise ApiError(409, "consent_already_recorded", "Consent was already recorded for this verification")
    if not body.accept:
        v.status = "cancelled"
        v.metadata_ = {**v.metadata_, "declined_by_person": "true"}
        db.add(v)
        await enqueue_event(db, org_id=v.org_id, env=v.env, event_type="verification.cancelled",
                            data={"id": v.id, "status": "cancelled", "reason": "consent_declined",
                                  "customer_ref": subject.customer_ref})
        await db.commit()
        return {**await _state(db, v, subject), "redirect_url": _redirect(v)}
    await consent.grant(db, org_id=v.org_id, subject=subject, scopes=v.scopes, purpose=v.purpose,
                        source="hosted_flow", ip=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"))
    v.status = "in_progress"
    db.add(v)
    cs.audit(db, org_id=v.org_id, actor_type="subject", actor_id=subject.id, action="consent.granted",
             target_type="verification", target_id=v.id, meta={"scopes": v.scopes},
             ip=request.client.host if request.client else None)
    await db.commit()
    return await _state(db, v, subject)


@router.post("/share-foid")
async def share_foid(token: str, user: Annotated[User, Depends(get_current_user)], db: Db) -> dict[str, Any]:
    """Signed-in FOID user: reuse what FOID has already verified instead of redoing it."""
    v, subject = await _load_open(db, token)
    if subject.user_id and subject.user_id != user.id:
        raise ApiError(409, "subject_linked_elsewhere", "This verification belongs to a different FOID account")
    if subject.user_id is None:
        await link(db, subject, user, "foid_share")
    for name in ("first_name", "middle_name", "last_name"):
        if not getattr(subject, name):
            setattr(subject, name, getattr(user, name))
    subject.email = subject.email or user.email
    db.add(subject)

    cred = (await db.exec(select(Credential).where(Credential.user_id == user.id))).first()
    claims: dict[str, Any] = dict(cred.claims) if cred else {}
    latest = await cs.latest_results(db, v.id)
    reused: list[str] = []

    if "nin" in v.checks and "nin" not in latest and claims.get("nin_verified"):
        subject.nin_hash, subject.nin_last4, subject.nin_verified = user.nin_hash, user.nin_last4, True
        await cs.save_result(db, subject=subject, check_type="nin", status="passed", reasons=[],
                             data={"source": "foid_credential", "nin_last4": user.nin_last4},
                             provider="foid", verification_id=v.id)
        reused.append("nin")

    if "liveness" in v.checks and "liveness" not in latest:
        enrolment = (await db.exec(select(FaceEnrolment).where(FaceEnrolment.user_id == user.id))).first()
        if enrolment is not None:
            face = (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == subject.id))).first()
            if face is None:
                face = SubjectFace(subject_id=subject.id, template_enc=enrolment.template_enc,
                                   face_png=enrolment.face_png, face_sha256=enrolment.face_sha256,
                                   receipt=enrolment.receipt, face_quality=enrolment.face_quality,
                                   model=enrolment.model)
                db.add(face)
            subject.liveness_passed_at = user.liveness_verified_at
            await cs.save_result(db, subject=subject, check_type="liveness", status="passed", reasons=[],
                                 data={"source": "foid_credential", "face_quality": enrolment.face_quality,
                                       "verified_at": cs.iso(user.liveness_verified_at)},
                                 provider="foid", verification_id=v.id)
            reused.append("liveness")

    v.reused_foid_credential = bool(reused) or v.reused_foid_credential
    db.add(v)
    cs.audit(db, org_id=v.org_id, actor_type="user", actor_id=user.id, action="foid_credential.shared",
             target_type="verification", target_id=v.id, meta={"reused": reused})
    await db.commit()
    return {**await _state(db, v, subject), "reused": reused}


# ---------------------------------------------------------------------------
# NIN / BVN steps
# ---------------------------------------------------------------------------

@router.post("/nin")
@limiter.limit("10/minute")
async def submit_nin(request: Request, token: str, body: NumberBody, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    await _step_guard(db, v, "nin")
    r = await cs.run_identity_check(db, subject=subject, kind="nin", number=body.number, verification_id=v.id)
    await db.commit()
    return _person_view(r)


@router.post("/nin-document")
@limiter.limit("6/minute")
async def submit_nin_document(request: Request, token: str, db: Db,
                              file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    await _step_guard(db, v, "nin")
    r = await cs.run_nin_document_check(db, subject=subject, file_bytes=await file.read(),
                                        mime_type=file.content_type or "", verification_id=v.id)
    await db.commit()
    return _person_view(r)


@router.post("/bvn")
@limiter.limit("10/minute")
async def submit_bvn(request: Request, token: str, body: NumberBody, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    await _step_guard(db, v, "bvn")
    r = await cs.run_identity_check(db, subject=subject, kind="bvn", number=body.number, verification_id=v.id)
    await db.commit()
    return _person_view(r)


# ---------------------------------------------------------------------------
# Liveness (same engine as first-party; owner = the subject)
# ---------------------------------------------------------------------------

def _liveness_check(v: Verification) -> Literal["liveness", "reverify"]:
    if "liveness" in v.checks:
        return "liveness"
    if "reverify" in v.checks:
        return "reverify"
    raise ApiError(400, "check_not_requested", "This verification does not include a liveness step")


@router.post("/liveness/start", status_code=201)
@limiter.limit("10/minute")
async def liveness_start(request: Request, token: str, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    check = _liveness_check(v)
    await _step_guard(db, v, check)
    run = ls.start_session(f"subject:{subject.id}", "enrol" if check == "liveness" else "verify")
    return {
        "session_id": run.nonce,
        "purpose": run.purpose,
        "challenges": run.challenges,
        "instructions": [ls.CHALLENGE_PROMPTS.get(c, c) for c in run.challenges],
        "expires_at": cs.iso(datetime.fromtimestamp(run.expires_at, tz=timezone.utc)),
    }


@router.post("/liveness/{session_id}/complete")
async def liveness_complete(token: str, session_id: str, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    check = _liveness_check(v)
    run = ls.get_session(session_id, f"subject:{subject.id}")
    final = run.final
    if final is None:
        raise ApiError(409, "liveness_not_finished", "Liveness session is not finished yet")
    ls.end_session(session_id)

    async def fail(reasons: list[str], data: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await cs.save_result(db, subject=subject, check_type=check, status="failed", reasons=reasons,
                                 data=data or {}, provider="faceliveness", verification_id=v.id)
        await db.commit()
        return {**_person_view(r), "passed": False, "message": "Liveness check failed — please try again"}

    if not final.passed or final.receipt is None or final.face_png is None:
        return await fail([final.fail_reason or "no_face_captured"])
    try:
        accepted = await fm.accept_face_record(db=db, subject_id=subject.id, purpose=check,
                                               receipt=final.receipt, face_png=final.face_png)
        embedding = await run_in_threadpool(fm.embed, accepted.face_png)
    except HTTPException as exc:
        return await fail(["face_record_rejected"], {"message": str(exc.detail)})
    except ValueError as exc:
        return await fail(["face_unreadable"], {"message": str(exc)})

    face = (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == subject.id))).first()
    if check == "liveness":
        if face is None:
            face = SubjectFace(subject_id=subject.id, template_enc=b"", face_png=b"", face_sha256="",
                               receipt="", face_quality=0.0, model=fm.MODEL_NAME)
        face.template_enc = fm.encrypt_template(embedding)
        face.face_png, face.face_sha256 = accepted.face_png, accepted.face_sha256
        face.receipt, face.face_quality, face.model = final.receipt, accepted.quality, fm.MODEL_NAME
        db.add(face)
        subject.liveness_passed_at = cs.utcnow()
        db.add(subject)
        r = await cs.save_result(db, subject=subject, check_type="liveness", status="passed", reasons=[],
                                 data={"face_quality": round(accepted.quality, 3),
                                       "real_score": accepted.real_score, "receipt_nonce": accepted.nonce},
                                 provider="faceliveness", verification_id=v.id)
        await db.flush()
        await link_user_for_subject(db, subject)
    else:
        if face is None:
            return await fail(["no_face_on_file"])
        score = fm.cosine(embedding, fm.decrypt_template(face.template_enc))
        matched = fm.is_match(score)
        r = await cs.save_result(db, subject=subject, check_type="reverify",
                                 status="passed" if matched else "failed",
                                 reasons=[] if matched else ["face_mismatch"],
                                 data={"match_score": round(score, 4), "matched": matched,
                                       "face_quality": round(accepted.quality, 3), "receipt_nonce": accepted.nonce},
                                 provider="faceliveness", verification_id=v.id)
    await db.commit()
    return {**_person_view(r), "passed": r.status == "passed",
            "message": "Liveness confirmed" if r.status == "passed" else "Face did not match — please try again"}


# ---------------------------------------------------------------------------
# Finish
# ---------------------------------------------------------------------------

@router.post("/finish")
async def finish(token: str, db: Db) -> dict[str, Any]:
    v, subject = await _load_open(db, token)
    await cs.complete_verification(db, v)
    await db.commit()
    return {**await _state(db, v, subject), "redirect_url": _redirect(v)}
