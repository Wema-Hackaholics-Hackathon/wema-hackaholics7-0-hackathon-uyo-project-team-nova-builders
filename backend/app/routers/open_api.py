"""FOID Open API v1 — for businesses, authenticated with secret API keys.

Mounted at /api/open/v1. Two ways to verify a person:

1. Hosted verification (recommended — FOID collects consent and runs the UI):
     POST /verifications {checks: ["nin","liveness"], customer_ref, first_name, last_name, ...}
       → {id, hosted_url, client_token}
     Send the person to hosted_url (or embed it with foid-verify.js). Results arrive
     by webhook `verification.completed`, or GET /verifications/{id}.

2. Server-to-server checks (you already collected the data and the consent):
     POST /checks/nin | /checks/bvn | /checks/nin-document

Every response about a person is filtered by the consent that person gave; once
they revoke it, data endpoints return 403 `consent_revoked`.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_auth import ApiContext, get_api_context, rate_limit_key
from app.core.api_errors import ApiError
from app.core.crypto import new_token, sha256_hex
from app.models import CheckResult, Credential, IdempotencyRecord, Notification, Subject, SubjectFace, Verification
from app.services import checks_service as cs
from app.services import consent_service as consent
from app.services.webhook_service import enqueue_event
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/open/v1", tags=["open-api"])

_RATE = "120/minute"
_EXTRA_SCOPES = ("contact", "financial")

Ctx = Annotated[ApiContext, Depends(get_api_context)]
Db = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PersonFields(BaseModel):
    customer_ref: str | None = Field(default=None, max_length=128, description="Your own id for this person")
    subject_id: str | None = None
    first_name: str | None = Field(default=None, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    date_of_birth: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)

    def person(self) -> dict[str, str | None]:
        return {
            "first_name": self.first_name, "middle_name": self.middle_name, "last_name": self.last_name,
            "date_of_birth": self.date_of_birth, "email": str(self.email) if self.email else None,
            "phone": self.phone,
        }


class CreateVerification(PersonFields):
    checks: list[Literal["nin", "bvn", "liveness", "reverify"]] = Field(min_length=1)
    scopes: list[Literal["contact", "financial"]] = Field(default_factory=list)
    purpose: str = Field(min_length=3, max_length=200, description="Shown to the person on the consent screen")
    return_url: str | None = Field(default=None, max_length=500)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("checks")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("checks must be unique")
        if "liveness" in v and "reverify" in v:
            raise ValueError("use either liveness (first time) or reverify (against the face on file)")
        return v


class ConsentAttestation(BaseModel):
    obtained: Literal[True] = Field(description="You confirm you collected the person's consent for this check")
    purpose: str = Field(min_length=3, max_length=200)


class IdentityCheckRequest(PersonFields):
    number: str = Field(description="11-digit NIN or BVN")
    consent: ConsentAttestation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _idempotent(request: Request, ctx: ApiContext, db: AsyncSession, payload: Any, handler: Any) -> JSONResponse:
    """Replay the stored response for a repeated Idempotency-Key (24 h semantics by cleanup)."""
    key = request.headers.get("idempotency-key")
    if not key:
        status_code, body = await handler()
        return JSONResponse(status_code=status_code, content=body)
    req_hash = sha256_hex(request.url.path + json.dumps(payload, sort_keys=True, default=str))
    existing = (await db.exec(select(IdempotencyRecord).where(
        IdempotencyRecord.org_id == ctx.org.id, IdempotencyRecord.env == ctx.env, IdempotencyRecord.key == key,
    ))).first()
    if existing is not None:
        if existing.request_hash != req_hash:
            raise ApiError(409, "idempotency_key_reused", "This Idempotency-Key was used with a different request")
        return JSONResponse(status_code=existing.status_code, content=existing.response,
                            headers={"Idempotent-Replayed": "true"})
    status_code, body = await handler()
    db.add(IdempotencyRecord(org_id=ctx.org.id, env=ctx.env, key=key[:255], request_hash=req_hash,
                             status_code=status_code, response=body))
    await db.commit()
    return JSONResponse(status_code=status_code, content=body)


async def _attest_consent(db: AsyncSession, ctx: ApiContext, subject: Subject, purpose: str, request: Request) -> None:
    """Server-to-server checks: the business attests it collected consent itself."""
    if "identity" in await consent.granted_scopes(db, ctx.org.id, subject.id):
        return
    await consent.grant(db, org_id=ctx.org.id, subject=subject, scopes=["identity"], purpose=purpose,
                        source="business_attested", ip=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"))


async def _get_verification(db: AsyncSession, ctx: ApiContext, verification_id: str) -> Verification:
    v = await db.get(Verification, verification_id)
    if v is None or v.org_id != ctx.org.id or v.env != ctx.env:
        raise ApiError(404, "verification_not_found", "No such verification")
    return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/ping")
async def ping(ctx: Ctx, db: Db) -> dict[str, Any]:
    await db.commit()   # persist key.last_used_at
    return {"ok": True, "organisation": ctx.org.name, "env": ctx.env}


@router.post("/verifications", status_code=201)
@limiter.limit(_RATE, key_func=rate_limit_key)
async def create_verification(request: Request, body: CreateVerification, ctx: Ctx, db: Db) -> JSONResponse:
    async def handler() -> tuple[int, dict[str, Any]]:
        subject = await cs.upsert_subject(db, org_id=ctx.org.id, env=ctx.env, subject_id=body.subject_id,
                                          customer_ref=body.customer_ref, **body.person())
        if "reverify" in body.checks:
            face = (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == subject.id))).first()
            if face is None:
                raise ApiError(409, "no_face_on_file",
                               "reverify needs a previous liveness check for this subject", "checks")
        token = new_token("vs_", 24)
        v = Verification(
            org_id=ctx.org.id, env=ctx.env, subject_id=subject.id, checks=list(body.checks),
            scopes=cs.scopes_for_checks(list(body.checks), list(body.scopes)), purpose=body.purpose,
            session_token_hash=sha256_hex(token), return_url=body.return_url, metadata_=body.metadata,
            expires_at=cs.verification_expiry(),
        )
        db.add(v)
        cs.audit(db, org_id=ctx.org.id, actor_type="api_key", actor_id=ctx.key.id,
                 action="verification.created", target_type="verification", target_id=v.id)
        await db.flush()
        out = await cs.serialize_verification(db, v, subject, include_token_url=cs.hosted_url(token))
        out["client_token"] = token
        await db.commit()
        return 201, out

    return await _idempotent(request, ctx, db, body.model_dump(mode="json"), handler)


@router.get("/verifications")
async def list_verifications(
    ctx: Ctx, db: Db,
    status: str | None = None, customer_ref: str | None = None,
    limit: int = 20, offset: int = 0,
) -> dict[str, Any]:
    q = select(Verification).where(Verification.org_id == ctx.org.id, Verification.env == ctx.env)
    if status:
        q = q.where(Verification.status == status)
    if customer_ref:
        q = q.join(Subject, Subject.id == Verification.subject_id).where(Subject.customer_ref == customer_ref)  # pyright: ignore[reportArgumentType]
    rows = (await db.exec(q.order_by(Verification.created_at.desc()).offset(offset).limit(min(limit, 100)))).all()  # pyright: ignore[reportAttributeAccessIssue]
    data = [await cs.serialize_verification(db, v, await db.get(Subject, v.subject_id)) for v in rows]
    return {"object": "list", "data": data, "has_more": len(rows) == min(limit, 100)}


@router.get("/verifications/{verification_id}")
async def get_verification(verification_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    v = await _get_verification(db, ctx, verification_id)
    return await cs.serialize_verification(db, v, await db.get(Subject, v.subject_id))


@router.post("/verifications/{verification_id}/cancel")
async def cancel_verification(verification_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    v = await _get_verification(db, ctx, verification_id)
    if v.status in ("completed", "cancelled"):
        raise ApiError(409, "verification_closed", f"Verification is already {v.status}")
    v.status = "cancelled"
    db.add(v)
    await enqueue_event(db, org_id=v.org_id, env=v.env, event_type="verification.cancelled",
                        subject_id=v.subject_id, data={"id": v.id, "status": "cancelled"})
    await db.commit()
    return await cs.serialize_verification(db, v, await db.get(Subject, v.subject_id))


async def _identity_check(kind: str, request: Request, body: IdentityCheckRequest, ctx: ApiContext,
                          db: AsyncSession) -> JSONResponse:
    async def handler() -> tuple[int, dict[str, Any]]:
        subject = await cs.upsert_subject(db, org_id=ctx.org.id, env=ctx.env, subject_id=body.subject_id,
                                          customer_ref=body.customer_ref, **body.person())
        await _attest_consent(db, ctx, subject, body.consent.purpose, request)
        result = await cs.run_identity_check(db, subject=subject, kind=kind, number=body.number)
        await db.commit()
        return 200, {**cs.serialize_check(result), "customer_ref": subject.customer_ref}

    payload = body.model_dump(mode="json")
    payload["number"] = sha256_hex(payload["number"])   # never persist the raw number in idempotency records
    return await _idempotent(request, ctx, db, payload, handler)


@router.post("/checks/nin")
@limiter.limit(_RATE, key_func=rate_limit_key)
async def check_nin(request: Request, body: IdentityCheckRequest, ctx: Ctx, db: Db) -> JSONResponse:
    """Look up an NIN and match it against the name / date of birth you send."""
    return await _identity_check("nin", request, body, ctx, db)


@router.post("/checks/bvn")
@limiter.limit(_RATE, key_func=rate_limit_key)
async def check_bvn(request: Request, body: IdentityCheckRequest, ctx: Ctx, db: Db) -> JSONResponse:
    """Look up a BVN and match it against the name / date of birth you send."""
    return await _identity_check("bvn", request, body, ctx, db)


@router.post("/checks/nin-document")
@limiter.limit("30/minute", key_func=rate_limit_key)
async def check_nin_document(
    request: Request,
    ctx: Ctx,
    db: Db,
    file: Annotated[UploadFile, File(description="Photo/scan of an NIN slip or NIMC card")],
    consent_obtained: Annotated[bool, Form()],
    purpose: Annotated[str, Form(min_length=3, max_length=200)],
    customer_ref: Annotated[str | None, Form()] = None,
    subject_id: Annotated[str | None, Form()] = None,
    first_name: Annotated[str | None, Form()] = None,
    middle_name: Annotated[str | None, Form()] = None,
    last_name: Annotated[str | None, Form()] = None,
    date_of_birth: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Extract the NIN from a document image (OCR), then look it up. The document photo is not used."""
    if not consent_obtained:
        raise ApiError(400, "consent_required", "consent_obtained must be true", "consent_obtained")
    subject = await cs.upsert_subject(db, org_id=ctx.org.id, env=ctx.env, subject_id=subject_id,
                                      customer_ref=customer_ref, first_name=first_name, middle_name=middle_name,
                                      last_name=last_name, date_of_birth=date_of_birth)
    await _attest_consent(db, ctx, subject, purpose, request)
    result = await cs.run_nin_document_check(db, subject=subject, file_bytes=await file.read(),
                                             mime_type=file.content_type or "")
    await db.commit()
    return {**cs.serialize_check(result), "customer_ref": subject.customer_ref}


# ── Subjects ────────────────────────────────────────────────────────────────

@router.get("/subjects")
async def list_subjects(ctx: Ctx, db: Db, customer_ref: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    q = select(Subject).where(Subject.org_id == ctx.org.id, Subject.env == ctx.env)
    if customer_ref:
        q = q.where(Subject.customer_ref == customer_ref)
    rows = (await db.exec(q.order_by(Subject.created_at.desc()).offset(offset).limit(min(limit, 100)))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return {"object": "list", "data": [await cs.serialize_subject(db, s) for s in rows]}


@router.get("/subjects/{subject_id}")
async def get_subject(subject_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    s = await cs.get_subject(db, ctx.org.id, ctx.env, subject_id)
    if await consent.consent_status(db, ctx.org.id, s.id) == "revoked":
        raise ApiError(403, "consent_revoked", "The person has revoked this business's access to their data")
    return await cs.serialize_subject(db, s)


@router.get("/subjects/{subject_id}/checks")
async def list_subject_checks(subject_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    s = await cs.get_subject(db, ctx.org.id, ctx.env, subject_id)
    scopes = await consent.granted_scopes(db, ctx.org.id, s.id)
    if not scopes:
        await consent.require_scope(db, ctx.org.id, s.id, "identity")   # raises the right 403
    rows = (await db.exec(select(CheckResult).where(CheckResult.subject_id == s.id)
                          .order_by(CheckResult.created_at.desc()))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return {"object": "list",
            "data": [cs.serialize_check(r) for r in rows if consent.CHECK_SCOPES.get(r.type) in scopes]}


@router.delete("/subjects/{subject_id}", status_code=204)
async def delete_subject(subject_id: str, ctx: Ctx, db: Db) -> None:
    """Erase a subject and everything FOID holds about them for your business (checks, face, consent)."""
    s = await cs.get_subject(db, ctx.org.id, ctx.env, subject_id)
    cs.audit(db, org_id=ctx.org.id, actor_type="api_key", actor_id=ctx.key.id, action="subject.deleted",
             target_type="subject", target_id=s.id)
    await cs.erase_subject(db, s)
    await db.commit()


@router.get("/subjects/{subject_id}/trust-report")
async def trust_report(subject_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    """Financial trust signals + living credential state. FOID account holders only, scope `financial`.

    This is not a credit score and carries no lending recommendation — the decision stays with you.
    """
    s = await cs.get_subject(db, ctx.org.id, ctx.env, subject_id)
    await consent.require_scope(db, ctx.org.id, s.id, "financial")
    if s.user_id is None:
        raise ApiError(409, "no_foid_account", "Trust reports are only available for people with a FOID account")
    cred = (await db.exec(select(Credential).where(Credential.user_id == s.user_id))).first()
    if cred is None:
        raise ApiError(404, "credential_not_found", "This person has no FOID credential yet")
    claims: dict[str, Any] = dict(cred.claims)
    checks = {k: bool(claims.get(k)) for k in
              ("email_verified", "nin_verified", "bvn_validated", "identity_verified", "phone_verified", "bill_verified")}
    weights = {"email_verified": 10, "nin_verified": 20, "bvn_validated": 20, "identity_verified": 25,
               "phone_verified": 10, "bill_verified": 15}
    notes = (await db.exec(select(Notification).where(Notification.user_id == s.user_id)
                           .order_by(Notification.timestamp.desc()).limit(10))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "object": "trust_report",
        "subject_id": s.id,
        "credential_state": cred.state,
        "income_band": claims.get("income_band"),
        "account_stability": claims.get("account_stability"),
        "repayment_reliability": claims.get("repayment_reliability"),
        "verification_completeness": sum(w for k, w in weights.items() if checks[k]),
        "verifications": checks,
        "signals": [
            {"message": n.message, "change": n.change, "reason": n.reason, "at": cs.iso(n.timestamp)}
            for n in notes if "→" in n.change
        ],
        "last_refreshed_at": cs.iso(cred.updated_at),
        "disclaimer": "Verified signals only. FOID does not score creditworthiness or recommend lending decisions.",
    }
