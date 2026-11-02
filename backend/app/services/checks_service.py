"""Checks + verifications for the business platform.

Shared by the server-to-server Open API (routers/open_api.py) and the hosted
verification page (routers/hosted.py).

Check types
  nin       NIN lookup by number, or by scanning an NIN slip / NIMC card
            (method="document": OCR extracts the NIN, which is then looked up)
  bvn       BVN lookup
  liveness  FOID-hosted liveness (faceliveness SDK) — stores the subject's face
  reverify  liveness + 1:1 match against the subject's stored face

Raw NIN/BVN numbers are never stored: subjects keep a keyed hash + last 4.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.api_errors import ApiError
from app.core.cascade import delete_cascade
from app.core.crypto import decrypt_str, mask, pii_hash
from app.models import (
    AuditLog,
    CheckResult,
    Organisation,
    Subject,
    UsageEvent,
    Verification,
    WebhookDelivery,
)
from app.services import groq_service
from app.services.consent_service import CHECK_SCOPES, consent_status, granted_scopes
from app.services.identity import ProviderUnavailable, get_provider
from app.services.identity.base import match_record
from app.services.identity.mock import MockProvider
from app.services.subject_link_service import link_user_for_subject
from app.services.webhook_service import enqueue_event

CHECK_TYPES = ("nin", "bvn", "liveness", "reverify")
MAX_ATTEMPTS_PER_CHECK = 3
_DOC_MIN_OCR_CONFIDENCE = 0.6
_DOC_MAX_BYTES = 8 * 1024 * 1024
_DOC_MIME = {"image/jpeg", "image/png", "image/webp"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    d = as_utc(dt)
    return d.isoformat() if d else None


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

_SUBJECT_FIELDS = ("first_name", "middle_name", "last_name", "date_of_birth", "email", "phone")


async def get_subject(db: AsyncSession, org_id: str, env: str, subject_id: str) -> Subject:
    s = await db.get(Subject, subject_id)
    if s is None or s.org_id != org_id or s.env != env:
        raise ApiError(404, "subject_not_found", "No such subject", "subject_id")
    return s


async def upsert_subject(
    db: AsyncSession,
    *,
    org_id: str,
    env: str,
    subject_id: str | None = None,
    customer_ref: str | None = None,
    **fields: str | None,
) -> Subject:
    """Find by id or customer_ref (per org + env), else create. Only non-empty fields overwrite."""
    subject: Subject | None = None
    if subject_id:
        subject = await get_subject(db, org_id, env, subject_id)
    elif customer_ref:
        subject = (await db.exec(
            select(Subject).where(Subject.org_id == org_id, Subject.env == env, Subject.customer_ref == customer_ref)
        )).first()
    if subject is None:
        subject = Subject(org_id=org_id, env=env, customer_ref=customer_ref)
    for name in _SUBJECT_FIELDS:
        value = fields.get(name)
        if value:
            setattr(subject, name, value.strip())
    subject.updated_at = utcnow()
    db.add(subject)
    await db.flush()
    return subject


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------

def record_usage(db: AsyncSession, *, org_id: str, env: str, check_type: str,
                 subject_id: str | None, verification_id: str | None) -> None:
    db.add(UsageEvent(
        org_id=org_id, env=env, check_type=check_type, subject_id=subject_id,
        verification_id=verification_id, billable=env == "live",
    ))


def audit(db: AsyncSession, *, org_id: str | None, actor_type: str, actor_id: str | None, action: str,
          target_type: str | None = None, target_id: str | None = None,
          meta: dict[str, Any] | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(org_id=org_id, actor_type=actor_type, actor_id=actor_id, action=action,
                    target_type=target_type, target_id=target_id, meta=meta or {}, ip=ip))


async def save_result(
    db: AsyncSession,
    *,
    subject: Subject,
    check_type: str,
    status: str,
    reasons: list[str],
    data: dict[str, Any],
    provider: str | None,
    verification_id: str | None = None,
) -> CheckResult:
    result = CheckResult(
        org_id=subject.org_id, env=subject.env, subject_id=subject.id, verification_id=verification_id,
        type=check_type, status=status, reasons=reasons, data=data, provider=provider,
    )
    db.add(result)
    if status != "error":
        record_usage(db, org_id=subject.org_id, env=subject.env, check_type=check_type,
                     subject_id=subject.id, verification_id=verification_id)
    await db.flush()
    if verification_id is None:   # direct API checks notify immediately; hosted flows notify on completion
        await enqueue_event(
            db, org_id=subject.org_id, env=subject.env, event_type="check.completed",
            subject_id=subject.id, data=serialize_check(result),
        )
    return result


# ---------------------------------------------------------------------------
# NIN / BVN
# ---------------------------------------------------------------------------

def _clean_number(value: str, kind: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 11:
        raise ApiError(400, f"invalid_{kind}", f"{kind.upper()} must be exactly 11 digits", kind)
    return digits


async def run_identity_check(
    db: AsyncSession,
    *,
    subject: Subject,
    kind: str,                         # nin | bvn
    number: str,
    method: str = "number",
    verification_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> CheckResult:
    number = _clean_number(number, kind)
    data: dict[str, Any] = {"method": method, f"{kind}_last4": number[-4:], **(extra or {})}
    try:
        provider = get_provider(subject.env)
        if isinstance(provider, MockProvider):
            provider.expect(subject.first_name, subject.middle_name, subject.last_name, subject.date_of_birth)
        record = await (provider.lookup_nin(number) if kind == "nin" else provider.lookup_bvn(number))
    except ProviderUnavailable as exc:
        return await save_result(db, subject=subject, check_type=kind, status="error",
                                 reasons=["provider_unavailable"], data={**data, "message": str(exc)},
                                 provider=None, verification_id=verification_id)

    if not record.found:
        return await save_result(db, subject=subject, check_type=kind, status="failed", reasons=["not_found"],
                                 data=data, provider=provider.name, verification_id=verification_id)

    match = match_record(record, subject.first_name, subject.last_name, subject.middle_name, subject.date_of_birth)
    reasons: list[str] = []
    if not (subject.first_name and subject.last_name):
        reasons.append("name_not_supplied")
    elif not match.name_match:
        reasons.append("name_mismatch")
    if match.dob_match is False:
        reasons.append("dob_mismatch")
    status = "failed" if reasons else "passed"
    if status == "passed" and method == "document" and (extra or {}).get("ocr_confidence", 1.0) < _DOC_MIN_OCR_CONFIDENCE:
        status, reasons = "needs_review", ["low_ocr_confidence"]

    data.update({
        "name_match": match.name_match,
        "name_score": match.name_score,
        "dob_match": match.dob_match,
        "record": {
            "first_name": record.first_name,
            "middle_name": record.middle_name,
            "last_name": record.last_name,
            "date_of_birth": record.date_of_birth,
        },
    })
    if status == "passed":
        setattr(subject, f"{kind}_hash", pii_hash(number))
        setattr(subject, f"{kind}_last4", number[-4:])
        setattr(subject, f"{kind}_verified", True)
        subject.updated_at = utcnow()
        db.add(subject)
        if kind == "nin":
            await db.flush()
            await link_user_for_subject(db, subject)
    return await save_result(db, subject=subject, check_type=kind, status=status, reasons=reasons, data=data,
                             provider=provider.name, verification_id=verification_id)


async def run_nin_document_check(
    db: AsyncSession,
    *,
    subject: Subject,
    file_bytes: bytes,
    mime_type: str,
    verification_id: str | None = None,
) -> CheckResult:
    """Scan of an NIN slip / NIMC card → OCR the NIN → normal NIN lookup.

    Only the NIN (and the printed name, for information) is taken from the
    document. The photo on it is NOT used for face matching.
    """
    if mime_type not in _DOC_MIME:
        raise ApiError(400, "unsupported_file_type", "Upload a JPEG, PNG or WebP image", "file")
    if not file_bytes or len(file_bytes) > _DOC_MAX_BYTES:
        raise ApiError(413, "file_too_large", "Image missing or larger than 8 MB", "file")
    try:
        parsed = await groq_service.extract_nin_document(file_bytes, mime_type)
    except groq_service.OcrUnavailable as exc:
        return await save_result(db, subject=subject, check_type="nin", status="error",
                                 reasons=["ocr_unavailable"], data={"method": "document", "message": str(exc)},
                                 provider=None, verification_id=verification_id)
    doc_type = parsed.get("document_type") or "unreadable"
    nin = re.sub(r"\D", "", parsed.get("nin") or "")
    extra = {
        "document_type": doc_type,
        "ocr_confidence": float(parsed.get("confidence") or 0.0),
        "printed_name": " ".join(p for p in (parsed.get("first_name"), parsed.get("middle_name"), parsed.get("last_name")) if p) or None,
    }
    if doc_type in ("other", "unreadable") or len(nin) != 11:
        reason = "unsupported_document" if doc_type == "other" else "document_unreadable"
        return await save_result(db, subject=subject, check_type="nin", status="failed", reasons=[reason],
                                 data={"method": "document", **extra}, provider="ocr",
                                 verification_id=verification_id)
    # Fill the name from the document if the business didn't supply one.
    if not subject.first_name and parsed.get("first_name"):
        subject.first_name = parsed["first_name"]
    if not subject.last_name and parsed.get("last_name"):
        subject.last_name = parsed["last_name"]
    return await run_identity_check(db, subject=subject, kind="nin", number=nin, method="document",
                                    verification_id=verification_id, extra=extra)


# ---------------------------------------------------------------------------
# Verifications (hosted flows)
# ---------------------------------------------------------------------------

def scopes_for_checks(checks: list[str], extra: list[str] | None = None) -> list[str]:
    return sorted({CHECK_SCOPES[c] for c in checks} | set(extra or []))


def hosted_url(token: str) -> str:
    return f"{get_settings().PUBLIC_APP_URL.rstrip('/')}/verify/{token}"


def verification_expiry() -> datetime:
    return utcnow() + timedelta(hours=get_settings().VERIFICATION_TTL_HOURS)


async def latest_results(db: AsyncSession, verification_id: str) -> dict[str, CheckResult]:
    rows = (await db.exec(
        select(CheckResult).where(CheckResult.verification_id == verification_id).order_by(CheckResult.created_at)  # pyright: ignore[reportArgumentType]
    )).all()
    latest: dict[str, CheckResult] = {}
    for r in rows:
        latest[r.type] = r
    return latest


async def attempts(db: AsyncSession, verification_id: str, check_type: str) -> int:
    rows = (await db.exec(
        select(CheckResult.id).where(CheckResult.verification_id == verification_id, CheckResult.type == check_type)
    )).all()
    return len(rows)


def outcome_of(checks: list[str], latest: dict[str, CheckResult]) -> str:
    statuses = [latest[c].status if c in latest else "failed" for c in checks]
    if all(s == "passed" for s in statuses):
        return "passed"
    if any(s in ("failed", "error") for s in statuses):
        return "failed"
    return "needs_review"


async def complete_verification(db: AsyncSession, v: Verification) -> Verification:
    """Close the verification, compute the outcome and notify the business (caller commits)."""
    if v.status in ("completed", "cancelled", "expired"):
        return v
    latest = await latest_results(db, v.id)
    v.outcome = outcome_of(v.checks, latest)
    v.status, v.completed_at = "completed", utcnow()
    db.add(v)
    subject = await db.get(Subject, v.subject_id)
    await db.flush()
    await enqueue_event(
        db, org_id=v.org_id, env=v.env, event_type="verification.completed", subject_id=v.subject_id,
        data=await serialize_verification(db, v, subject),
    )
    return v


def ensure_open(v: Verification) -> None:
    if v.status in ("completed", "cancelled"):
        raise ApiError(410, "verification_closed", f"This verification is {v.status}")
    if (as_utc(v.expires_at) or utcnow()) < utcnow():
        raise ApiError(410, "verification_expired", "This verification link has expired")


# ---------------------------------------------------------------------------
# Serialisation (consent-aware)
# ---------------------------------------------------------------------------

def serialize_check(r: CheckResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "type": r.type,
        "status": r.status,
        "reasons": r.reasons,
        "data": r.data,
        "provider": r.provider,
        "verification_id": r.verification_id,
        "subject_id": r.subject_id,
        "created_at": iso(r.created_at),
    }


async def serialize_subject(db: AsyncSession, s: Subject) -> dict[str, Any]:
    status = await consent_status(db, s.org_id, s.id)
    scopes = await granted_scopes(db, s.org_id, s.id)
    out: dict[str, Any] = {
        "id": s.id,
        "customer_ref": s.customer_ref,
        "env": s.env,
        "consent": {"status": status, "scopes": sorted(scopes)},
        "has_foid_account": s.user_id is not None,
        "created_at": iso(s.created_at),
    }
    if "identity" in scopes:
        out.update({
            "first_name": s.first_name, "middle_name": s.middle_name, "last_name": s.last_name,
            "date_of_birth": s.date_of_birth,
            "nin": {"verified": s.nin_verified, "last4": s.nin_last4},
            "bvn": {"verified": s.bvn_verified, "last4": s.bvn_last4},
        })
    if "contact" in scopes:
        out.update({"email": s.email, "phone": mask(s.phone, 4) if s.phone else None})
    if "liveness" in scopes:
        out["liveness"] = {"passed_at": iso(s.liveness_passed_at)}
    return out


def open_link(v: Verification) -> dict[str, str] | None:
    """hosted_url + client_token while the verification can still be completed; else None."""
    if v.session_token_enc is None or v.status not in ("pending", "in_progress"):
        return None
    if (as_utc(v.expires_at) or utcnow()) < utcnow():
        return None
    token = decrypt_str(v.session_token_enc)
    return {"hosted_url": hosted_url(token), "client_token": token}


async def serialize_verification(db: AsyncSession, v: Verification, subject: Subject | None,
                                 include_link: bool = False) -> dict[str, Any]:
    """include_link: add hosted_url/client_token (business-facing reads only — never in webhooks)."""
    scopes = await granted_scopes(db, v.org_id, v.subject_id)
    c_status = await consent_status(db, v.org_id, v.subject_id)
    latest = await latest_results(db, v.id)
    results: dict[str, Any] = {}
    for c in v.checks:
        r = latest.get(c)
        if r is None:
            results[c] = {"status": "pending"}
        elif CHECK_SCOPES[c] in scopes:
            results[c] = serialize_check(r)
        else:   # consent revoked / not granted — status only, no personal data
            results[c] = {"status": r.status, "redacted": True}
    out: dict[str, Any] = {
        "id": v.id,
        "object": "verification",
        "env": v.env,
        "status": v.status,
        "outcome": v.outcome,
        "checks": v.checks,
        "scopes": v.scopes,
        "purpose": v.purpose,
        "subject_id": v.subject_id,
        "customer_ref": subject.customer_ref if subject else None,
        "consent": {"status": c_status, "scopes": sorted(scopes)},
        "reused_foid_credential": v.reused_foid_credential,
        "results": results,
        "metadata": v.metadata_,
        "expires_at": iso(v.expires_at),
        "completed_at": iso(v.completed_at),
        "created_at": iso(v.created_at),
    }
    if include_link:
        out.update(open_link(v) or {"hosted_url": None, "client_token": None})
    return out


async def org_branding(db: AsyncSession, org_id: str) -> dict[str, Any]:
    org = await db.get(Organisation, org_id)
    return {
        "name": org.name if org else "Unknown business",
        "logo_url": org.logo_url if org else None,
        "brand_color": org.brand_color if org else None,
        "website": org.website if org else None,
        "support_email": org.support_email if org else None,
    }


# ---------------------------------------------------------------------------
# Erasure + expiry
# ---------------------------------------------------------------------------

async def erase_subject(db: AsyncSession, subject: Subject) -> None:
    """Delete a subject and everything hanging off it (see core/cascade.py)."""
    pending = (await db.exec(select(WebhookDelivery).where(
        WebhookDelivery.subject_id == subject.id, WebhookDelivery.status == "pending"))).all()
    for d in pending:
        d.status, d.last_error = "cancelled", "subject deleted"
        db.add(d)
    await db.flush()
    await delete_cascade(db, "subjects", [subject.id])


async def expire_stale_verifications(session_factory: Any) -> int:
    """Mark unfinished verifications past their expiry as expired and tell the business."""
    async with session_factory() as db:
        now = utcnow()
        rows = (await db.exec(select(Verification).where(
            Verification.status.in_(("pending", "in_progress")),  # pyright: ignore[reportAttributeAccessIssue]
            Verification.expires_at < now,
        ))).all()
        for v in rows:
            v.status = "expired"
            db.add(v)
            await enqueue_event(db, org_id=v.org_id, env=v.env, event_type="verification.expired",
                                subject_id=v.subject_id, data={"id": v.id, "status": "expired"})
        await db.commit()
        return len(rows)
