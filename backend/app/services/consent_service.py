"""Consent grants between a subject (person) and an organisation (business).

Rules
- A business can only read a subject's data while it holds an ACTIVE grant
  covering the scope it asks for (require_scope).
- Revoking stops everything at once: data endpoints return 403
  `consent_revoked`, queued webhooks about that subject are cancelled, and no new
  events are sent. The business gets exactly one `consent.revoked` event so it
  knows to stop using what it already has.
- Who can revoke: the person (FOID "Connected apps", once their FOID account is
  linked to the subject), the business itself, or a FOID admin.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_errors import ApiError
from app.models import AuditLog, ConsentGrant, Notification, Organisation, Subject
from app.services.webhook_service import cancel_pending_for_subject, enqueue_event

# scope → what it unlocks
SCOPES: dict[str, str] = {
    "identity": "NIN / BVN check results and the name & date of birth on record",
    "liveness": "Liveness results and re-verification against the captured face",
    "contact": "Email address and phone number",
    "financial": "Trust report and credential state changes (FOID account holders only)",
}

CHECK_SCOPES: dict[str, str] = {
    "nin": "identity",
    "bvn": "identity",
    "liveness": "liveness",
    "reverify": "liveness",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def active_grants(db: AsyncSession, org_id: str, subject_id: str) -> list[ConsentGrant]:
    return list((await db.exec(
        select(ConsentGrant).where(
            ConsentGrant.org_id == org_id,
            ConsentGrant.subject_id == subject_id,
            ConsentGrant.status == "active",
        )
    )).all())


async def granted_scopes(db: AsyncSession, org_id: str, subject_id: str) -> set[str]:
    scopes: set[str] = set()
    for g in await active_grants(db, org_id, subject_id):
        scopes.update(g.scopes)
    return scopes


async def consent_status(db: AsyncSession, org_id: str, subject_id: str) -> str:
    """active | revoked | none"""
    if await active_grants(db, org_id, subject_id):
        return "active"
    any_grant = (await db.exec(
        select(ConsentGrant.id).where(ConsentGrant.org_id == org_id, ConsentGrant.subject_id == subject_id)
    )).first()
    return "revoked" if any_grant else "none"


async def require_scope(db: AsyncSession, org_id: str, subject_id: str, scope: str) -> None:
    scopes = await granted_scopes(db, org_id, subject_id)
    if scope in scopes:
        return
    if not scopes and await consent_status(db, org_id, subject_id) == "revoked":
        raise ApiError(403, "consent_revoked", "The person has revoked this business's access to their data")
    raise ApiError(403, "scope_not_granted", f"No active consent for scope '{scope}'")


async def grant(
    db: AsyncSession,
    *,
    org_id: str,
    subject: Subject,
    scopes: list[str],
    purpose: str,
    source: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ConsentGrant:
    g = ConsentGrant(
        org_id=org_id,
        subject_id=subject.id,
        user_id=subject.user_id,
        scopes=sorted(set(scopes)),
        purpose=purpose,
        source=source,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(g)
    return g


async def revoke_subject(
    db: AsyncSession,
    *,
    org_id: str,
    subject: Subject,
    by: str,
    actor_id: str | None,
) -> int:
    """Revoke every active grant this org holds for the subject. Caller commits."""
    grants = await active_grants(db, org_id, subject.id)
    if not grants:
        return 0
    now = _now()
    revoked_scopes: set[str] = set()
    for g in grants:
        g.status, g.revoked_at, g.revoked_by = "revoked", now, by
        revoked_scopes.update(g.scopes)
        db.add(g)
    await db.flush()
    await cancel_pending_for_subject(db, org_id, subject.id)
    if by != "business":
        from app.services.console_inbox import notify
        from app.services.console_views import subject_code
        code = subject_code(subject.id)
        await notify(db, org_id, "consent_revoked", f"{code} revoked consent",
                     "Their data is now hidden and no more updates are sent about them.",
                     link=f"/users?q={code}", min_role="reviewer")
    await enqueue_event(
        db,
        org_id=org_id,
        env=subject.env,
        event_type="consent.revoked",
        subject_id=subject.id,
        data={
            "subject_id": subject.id,
            "customer_ref": subject.customer_ref,
            "scopes": sorted(revoked_scopes),
            "revoked_by": by,
            "revoked_at": now.isoformat(),
        },
    )
    db.add(AuditLog(
        org_id=org_id, actor_type=by, actor_id=actor_id, action="consent.revoked",
        target_type="subject", target_id=subject.id, meta={"scopes": sorted(revoked_scopes)},
    ))
    if subject.user_id and by != "user":
        org = await db.get(Organisation, org_id)
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=subject.user_id,
            message=f"{org.name if org else 'A business'} no longer has access to your data",
            change="consent: active → revoked",
            reason=f"Access was revoked by the {by}.",
            action="No action needed.",
        ))
    return len(grants)
