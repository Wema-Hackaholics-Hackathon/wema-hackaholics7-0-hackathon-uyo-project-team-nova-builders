"""Business dashboard API — /api/v1/business/* (console account JWT + org membership).

Backs the business dashboard (designed separately): organisation profile &
branding, team, API keys, webhooks + delivery log, verifications, subjects,
usage and audit log. A console account (models/console.py — not a FOID user account) can belong to several organisations; every
route is scoped by {org_id} and checked against the caller's role.

Roles: owner > admin > developer > reviewer > viewer
  owner/admin  everything (admin can't remove owners)
  developer    API keys, webhooks, read everything
  reviewer     read verifications/subjects (manual review — later phase)
  viewer       read-only
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_auth import generate_api_key
from app.core.api_errors import ApiError
from app.core.crypto import encrypt_str, new_token
from app.core.dependencies import require_verified_console_user
from app.models import (
    ApiKey,
    AuditLog,
    CheckResult,
    ConsoleUser,
    Organisation,
    OrgMember,
    Subject,
    UsageEvent,
    Verification,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.services import checks_service as cs
from app.services import console_inbox, console_notify
from app.services import console_views as cv
from app.services.billing_service import PLANS
from app.services import consent_service as consent
from app.services import webhook_service as wh
from app.services.webhook_service import EVENT_TYPES, attempt, build_event
from app.services.webhook_urls import check_url

router = APIRouter(prefix="/business", tags=["business-dashboard"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]
Env = Literal["test", "live"]

MAX_UNAPPROVED_ORGS = 5   # businesses one account may own before any is approved for Live (anti-spam)
_RANK = {"viewer": 0, "reviewer": 1, "developer": 2, "admin": 3, "owner": 4}
ROLES = list(_RANK)


async def _member(db: AsyncSession, org_id: str, user: ConsoleUser, min_role: str = "viewer",
                  allow_deactivated: bool = False) -> OrgMember:
    """Membership + role check for every org route. Also enforces the org's 2FA rule and deactivation."""
    m = (await db.exec(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.console_user_id == user.id))).first()
    if m is None:
        raise ApiError(404, "organisation_not_found", "No such organisation")
    org = await db.get(Organisation, org_id)
    assert org is not None
    if org.require_2fa and user.totp_enabled_at is None:
        raise ApiError(403, "two_factor_required", f"{org.name} requires two-step sign-in — turn it on in My account")
    if org.status != "active" and not allow_deactivated:
        raise ApiError(423, "organisation_deactivated", f"{org.name} is deactivated — an owner can reactivate it in Settings")
    if _RANK[m.role] < _RANK[min_role]:
        raise ApiError(403, "insufficient_role", f"Requires the {min_role} role or higher")
    return m


def _org_out(org: Organisation, role: str | None = None) -> dict[str, Any]:
    return {
        "id": org.id, "name": org.name, "website": org.website, "support_email": org.support_email,
        "logo_url": org.logo_url, "brand_color": org.brand_color, "rc_number": org.rc_number,
        "kyb_status": org.kyb_status, "live_enabled": org.live_enabled, "status": org.status,
        "plan_code": org.plan_code, "plan": PLANS[org.plan_code]["name"],
        "require_2fa": org.require_2fa, "deactivated_at": cs.iso(org.deactivated_at),
        "created_at": cs.iso(org.created_at), "role": role,
    }


# ---------------------------------------------------------------------------
# Organisations
# ---------------------------------------------------------------------------

class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    website: HttpUrl | None = None
    support_email: EmailStr | None = None


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    website: HttpUrl | None = None
    support_email: EmailStr | None = None
    logo_url: HttpUrl | None = None
    brand_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


async def new_organisation(db: AsyncSession, owner: ConsoleUser, name: str,
                           website: str | None = None, support_email: str | None = None) -> Organisation:
    """Organisation + owner membership + audit entry. Caller commits. Also used by console signup."""
    org = Organisation(name=name, website=website, support_email=support_email, created_by=owner.id)
    db.add(org)
    await db.flush()
    db.add(OrgMember(org_id=org.id, console_user_id=owner.id, role="owner"))
    cs.audit(db, org_id=org.id, actor_type="member", actor_id=owner.id, action="organisation.created")
    return org


@router.post("/organisations", status_code=201)
async def create_org(body: OrgCreate, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Another business under the same console account (each has its own KYB, keys, users and billing)."""
    owned = (await db.exec(select(Organisation).join(OrgMember, col(OrgMember.org_id) == Organisation.id)
                           .where(OrgMember.console_user_id == user.id, OrgMember.role == "owner"))).all()
    if len(owned) >= MAX_UNAPPROVED_ORGS and not any(o.kyb_status == "approved" for o in owned):
        raise ApiError(403, "organisation_limit", f"You can own {MAX_UNAPPROVED_ORGS} businesses until one is approved for Live")
    org = await new_organisation(db, user, body.name, str(body.website) if body.website else None,
                                 str(body.support_email) if body.support_email else None)
    await db.commit()
    return _org_out(org, "owner")


@router.get("/organisations")
async def my_orgs(user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    rows = (await db.exec(select(Organisation, OrgMember.role).join(OrgMember, OrgMember.org_id == Organisation.id)  # pyright: ignore[reportArgumentType]
                          .where(OrgMember.console_user_id == user.id))).all()
    return [_org_out(o, role) for o, role in rows]


@router.get("/organisations/{org_id}")
async def get_org(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    m = await _member(db, org_id, user, allow_deactivated=True)
    org = await db.get(Organisation, org_id)
    assert org is not None
    return _org_out(org, m.role)


@router.patch("/organisations/{org_id}")
async def update_org(org_id: str, body: OrgUpdate, user: CurrentUser, db: Db) -> dict[str, Any]:
    m = await _member(db, org_id, user, "admin")
    org = await db.get(Organisation, org_id)
    assert org is not None
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(org, k, str(val) if val is not None else None)
    db.add(org)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="organisation.updated",
             meta=body.model_dump(mode="json", exclude_unset=True))
    await db.commit()
    return _org_out(org, m.role)


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class MemberAdd(BaseModel):
    email: EmailStr = Field(description="Must already have a FOID Console account (invites: later phase)")
    role: Literal["admin", "developer", "reviewer", "viewer"]


class MemberUpdate(BaseModel):
    role: Literal["admin", "developer", "reviewer", "viewer"]


@router.get("/organisations/{org_id}/members")
async def list_members(org_id: str, user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    await _member(db, org_id, user)
    rows = (await db.exec(select(OrgMember, ConsoleUser).join(ConsoleUser, ConsoleUser.id == OrgMember.console_user_id)  # pyright: ignore[reportArgumentType]
                          .where(OrgMember.org_id == org_id))).all()
    return [{"id": m.id, "console_user_id": u.id, "name": f"{u.first_name} {u.last_name}", "email": u.email,
             "last_active_at": cs.iso(u.last_active_at),
             "role": m.role, "joined_at": cs.iso(m.created_at)} for m, u in rows]


@router.post("/organisations/{org_id}/members", status_code=201)
async def add_member(org_id: str, body: MemberAdd, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    target = (await db.exec(select(ConsoleUser).where(ConsoleUser.email == str(body.email).lower()))).first()
    if target is None:
        raise ApiError(404, "user_not_found", "No FOID Console account uses that email — ask them to sign up to the console first", "email")
    exists = (await db.exec(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.console_user_id == target.id))).first()
    if exists:
        raise ApiError(409, "already_member", "That person is already a member")
    m = OrgMember(org_id=org_id, console_user_id=target.id, role=body.role)
    db.add(m)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="member.added",
             target_type="member", target_id=target.id, meta={"role": body.role})
    await db.commit()
    return {"id": m.id, "console_user_id": target.id, "email": target.email, "role": m.role}


@router.patch("/organisations/{org_id}/members/{member_id}")
async def update_member(org_id: str, member_id: str, body: MemberUpdate, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    m = await db.get(OrgMember, member_id)
    if m is None or m.org_id != org_id:
        raise ApiError(404, "member_not_found", "No such member")
    if m.role == "owner":
        raise ApiError(403, "cannot_change_owner", "The owner's role can't be changed")
    m.role = body.role
    db.add(m)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="member.role_changed",
             target_type="member", target_id=m.id, meta={"role": body.role})
    await db.commit()
    return {"id": m.id, "role": m.role}


@router.delete("/organisations/{org_id}/members/{member_id}", status_code=204)
async def remove_member(org_id: str, member_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "admin")
    m = await db.get(OrgMember, member_id)
    if m is None or m.org_id != org_id:
        raise ApiError(404, "member_not_found", "No such member")
    if m.role == "owner":
        raise ApiError(403, "cannot_remove_owner", "The owner can't be removed")
    await db.delete(m)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="member.removed",
             target_type="member", target_id=member_id)
    await db.commit()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class KeyCreate(BaseModel):
    env: Env
    name: str = Field(default="Default key", max_length=60)


def _key_out(k: ApiKey) -> dict[str, Any]:
    return {"id": k.id, "env": k.env, "name": k.name, "hint": k.prefix, "last_used_at": cs.iso(k.last_used_at),
            "revoked_at": cs.iso(k.revoked_at), "created_at": cs.iso(k.created_at)}


@router.get("/organisations/{org_id}/api-keys")
async def list_keys(org_id: str, user: CurrentUser, db: Db, env: Env | None = None,
                    include_revoked: bool = False) -> list[dict[str, Any]]:
    await _member(db, org_id, user, "developer")
    q = select(ApiKey).where(ApiKey.org_id == org_id)
    if env:
        q = q.where(ApiKey.env == env)
    if not include_revoked:
        q = q.where(ApiKey.revoked_at == None)  # noqa: E711
    rows = (await db.exec(q.order_by(ApiKey.created_at.desc()))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return [_key_out(k) for k in rows]


@router.post("/organisations/{org_id}/api-keys", status_code=201)
async def create_key(org_id: str, body: KeyCreate, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Returns the secret ONCE (`secret`). Live keys need an approved KYB."""
    await _member(db, org_id, user, "developer")
    org = await db.get(Organisation, org_id)
    assert org is not None
    if body.env == "live" and not org.live_enabled:
        raise ApiError(403, "live_mode_disabled", "Complete business verification (KYB) to create live keys")
    raw, prefix, key_hash = generate_api_key(body.env)
    k = ApiKey(org_id=org_id, env=body.env, name=body.name, prefix=prefix, key_hash=key_hash, created_by=user.id)
    db.add(k)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="api_key.created",
             target_type="api_key", target_id=k.id, meta={"env": body.env})
    await console_inbox.notify(db, org_id, "api_key_created", f"New {body.env} API key: {k.name}",
                               f"{user.first_name} {user.last_name} created {k.prefix}.", link="/api-keys",
                               min_role="admin", exclude=user.id)
    await db.commit()
    await console_notify.key_created(db, org, user, k)
    return {**_key_out(k), "secret": raw}


@router.post("/organisations/{org_id}/api-keys/{key_id}/rotate", status_code=201)
async def rotate_key(org_id: str, key_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    """New key with the same name and env; the old one stops working immediately. Secret shown ONCE."""
    await _member(db, org_id, user, "developer")
    old = await db.get(ApiKey, key_id)
    if old is None or old.org_id != org_id or old.revoked_at is not None:
        raise ApiError(404, "api_key_not_found", "No such active API key")
    raw, hint, key_hash = generate_api_key(old.env)
    new = ApiKey(org_id=org_id, env=old.env, name=old.name, prefix=hint, key_hash=key_hash, created_by=user.id)
    old.revoked_at = datetime.now(timezone.utc)
    db.add(old)
    db.add(new)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="api_key.rotated",
             target_type="api_key", target_id=new.id, meta={"env": old.env, "replaces": old.id})
    await console_inbox.notify(db, org_id, "api_key_created", f"{old.env.capitalize()} API key regenerated: {old.name}",
                               f"{user.first_name} {user.last_name} replaced {old.prefix} with {hint}.", link="/api-keys",
                               min_role="admin", exclude=user.id)
    await db.commit()
    org = await db.get(Organisation, org_id)
    assert org is not None
    await console_notify.key_created(db, org, user, new)
    return {**_key_out(new), "secret": raw}


@router.delete("/organisations/{org_id}/api-keys/{key_id}", status_code=204)
async def revoke_key(org_id: str, key_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "developer")
    k = await db.get(ApiKey, key_id)
    if k is None or k.org_id != org_id:
        raise ApiError(404, "api_key_not_found", "No such API key")
    if k.revoked_at is None:
        k.revoked_at = datetime.now(timezone.utc)
        db.add(k)
        cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="api_key.revoked",
                 target_type="api_key", target_id=k.id)
        await db.commit()


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

class WebhookCreate(BaseModel):
    env: Env
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["*"])


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    enabled: bool | None = None


def _check_events(events: list[str]) -> list[str]:
    bad = [e for e in events if e != "*" and e not in EVENT_TYPES]
    if bad:
        raise ApiError(400, "unknown_event_type", f"Unknown event types: {bad}. Valid: {EVENT_TYPES}", "events")
    return events


def _wh_out(w: WebhookEndpoint) -> dict[str, Any]:
    return {"id": w.id, "env": w.env, "url": w.url, "events": w.events, "enabled": w.enabled,
            "created_at": cs.iso(w.created_at)}


def _delivery_out(d: WebhookDelivery) -> dict[str, Any]:
    return {"id": d.id, "event_id": d.event_id, "event_type": d.event_type, "status": d.status,
            "attempts": d.attempts, "last_status_code": d.last_status_code, "last_error": d.last_error,
            "next_attempt_at": cs.iso(d.next_attempt_at) if d.status == "pending" else None,
            "delivered_at": cs.iso(d.delivered_at), "created_at": cs.iso(d.created_at), "payload": d.payload}


@router.get("/webhook-event-types")
async def webhook_event_types() -> list[str]:
    return EVENT_TYPES


@router.get("/organisations/{org_id}/webhooks")
async def list_webhooks(org_id: str, user: CurrentUser, db: Db, env: Env | None = None) -> list[dict[str, Any]]:
    """Each endpoint with its most recent delivery (status + time), for a health indicator."""
    await _member(db, org_id, user, "developer")
    q = select(WebhookEndpoint).where(WebhookEndpoint.org_id == org_id)
    if env:
        q = q.where(WebhookEndpoint.env == env)
    rows = (await db.exec(q.order_by(WebhookEndpoint.created_at))).all()  # pyright: ignore[reportArgumentType]
    out = []
    for w in rows:
        last = (await db.exec(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == w.id, WebhookDelivery.attempts > 0)
                              .order_by(WebhookDelivery.created_at.desc()).limit(1))).first()  # pyright: ignore[reportAttributeAccessIssue]
        # pending with attempts = the last try failed and a retry is scheduled
        status_ = ("retrying" if last.status == "pending" else last.status) if last else None
        out.append({**_wh_out(w), "last_delivery_status": status_,
                    "last_delivery_at": cs.iso(last.delivered_at or last.created_at) if last else None})
    return out


@router.post("/organisations/{org_id}/webhooks", status_code=201)
async def create_webhook(org_id: str, body: WebhookCreate, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Returns the signing secret ONCE (`secret`)."""
    await _member(db, org_id, user, "developer")
    secret = new_token("whsec_", 24)
    w = WebhookEndpoint(org_id=org_id, env=body.env, url=check_url(str(body.url), body.env), secret_enc=encrypt_str(secret),
                        events=_check_events(body.events))
    db.add(w)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="webhook.created",
             target_type="webhook", target_id=w.id)
    await db.commit()
    return {**_wh_out(w), "secret": secret}


async def _webhook(db: AsyncSession, org_id: str, webhook_id: str) -> WebhookEndpoint:
    w = await db.get(WebhookEndpoint, webhook_id)
    if w is None or w.org_id != org_id:
        raise ApiError(404, "webhook_not_found", "No such webhook endpoint")
    return w


@router.patch("/organisations/{org_id}/webhooks/{webhook_id}")
async def update_webhook(org_id: str, webhook_id: str, body: WebhookUpdate, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "developer")
    w = await _webhook(db, org_id, webhook_id)
    if body.url is not None:
        w.url = check_url(str(body.url), w.env)
    if body.events is not None:
        w.events = _check_events(body.events)
    if body.enabled is not None:
        w.enabled = body.enabled
    db.add(w)
    await db.commit()
    return _wh_out(w)


@router.post("/organisations/{org_id}/webhooks/{webhook_id}/roll-secret")
async def roll_webhook_secret(org_id: str, webhook_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "developer")
    w = await _webhook(db, org_id, webhook_id)
    secret = new_token("whsec_", 24)
    w.secret_enc = encrypt_str(secret)
    db.add(w)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="webhook.secret_rolled",
             target_type="webhook", target_id=w.id)
    await db.commit()
    return {**_wh_out(w), "secret": secret}


@router.delete("/organisations/{org_id}/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(org_id: str, webhook_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "developer")
    w = await _webhook(db, org_id, webhook_id)
    for d in (await db.exec(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == w.id))).all():
        await db.delete(d)
    await db.delete(w)
    await db.commit()


@router.post("/organisations/{org_id}/webhooks/{webhook_id}/test")
async def test_webhook(org_id: str, webhook_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Send a `webhook.test` event right now and return the delivery result."""
    await _member(db, org_id, user, "developer")
    w = await _webhook(db, org_id, webhook_id)
    event = build_event("webhook.test", w.env, {"message": "Hello from FOID"})
    d = WebhookDelivery(org_id=org_id, endpoint_id=w.id, event_id=event["id"], event_type="webhook.test",
                        payload=event)
    db.add(d)
    async with wh.new_client() as client:
        await attempt(db, d, client)
    await db.commit()
    return _delivery_out(d)


@router.get("/organisations/{org_id}/webhooks/{webhook_id}/deliveries")
async def list_deliveries(org_id: str, webhook_id: str, user: CurrentUser, db: Db,
                          status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    await _member(db, org_id, user, "developer")
    await _webhook(db, org_id, webhook_id)
    q = select(WebhookDelivery).where(WebhookDelivery.endpoint_id == webhook_id)
    if status:
        q = q.where(WebhookDelivery.status == status)
    rows = (await db.exec(q.order_by(WebhookDelivery.created_at.desc()).limit(min(limit, 200)))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return [_delivery_out(d) for d in rows]


@router.post("/organisations/{org_id}/webhooks/{webhook_id}/deliveries/{delivery_id}/retry")
async def retry_delivery(org_id: str, webhook_id: str, delivery_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "developer")
    d = await db.get(WebhookDelivery, delivery_id)
    if d is None or d.org_id != org_id or d.endpoint_id != webhook_id:
        raise ApiError(404, "delivery_not_found", "No such delivery")
    if d.status == "cancelled" and d.last_error == "consent revoked":
        raise ApiError(403, "consent_revoked", "The person revoked consent — this event can't be re-sent")
    d.status = "pending"
    async with wh.new_client() as client:
        await attempt(db, d, client)
    await db.commit()
    return _delivery_out(d)


# ---------------------------------------------------------------------------
# Verifications & subjects (dashboard views — same consent filtering as the API)
# ---------------------------------------------------------------------------

@router.get("/organisations/{org_id}/verifications")
async def dash_verifications(org_id: str, user: CurrentUser, db: Db, env: Env = "test",
                             status: str | None = None, outcome: str | None = None,
                             limit: int = 25, offset: int = 0) -> dict[str, Any]:
    await _member(db, org_id, user)
    q = select(Verification).where(Verification.org_id == org_id, Verification.env == env)
    if status:
        q = q.where(Verification.status == status)
    if outcome:
        q = q.where(Verification.outcome == outcome)
    rows = (await db.exec(q.order_by(Verification.created_at.desc()).offset(offset).limit(min(limit, 100)))).all()  # pyright: ignore[reportAttributeAccessIssue]
    out = []
    for v in rows:
        s = await db.get(Subject, v.subject_id)
        item = await cs.serialize_verification(db, v, s, include_link=True)
        scopes = await consent.granted_scopes(db, org_id, v.subject_id)
        item["subject_name"] = (" ".join(p for p in (s.first_name, s.last_name) if p)
                                if s and "identity" in scopes else None)
        out.append(item)
    return {"data": out, "limit": limit, "offset": offset}


@router.get("/organisations/{org_id}/verifications/{verification_id}")
async def dash_verification(org_id: str, verification_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user)
    v = await db.get(Verification, verification_id)
    if v is None or v.org_id != org_id:
        raise ApiError(404, "verification_not_found", "No such verification")
    s = await db.get(Subject, v.subject_id)
    out = await cs.serialize_verification(db, v, s, include_link=True)
    out["subject"] = await cs.serialize_subject(db, s) if s else None
    out["timeline"] = [
        {"action": a.action, "actor_type": a.actor_type, "at": cs.iso(a.created_at), "meta": a.meta}
        for a in (await db.exec(select(AuditLog).where(AuditLog.target_id == v.id)
                                .order_by(AuditLog.created_at))).all()  # pyright: ignore[reportArgumentType]
    ]
    return out


@router.get("/organisations/{org_id}/subjects")
async def dash_subjects(org_id: str, user: CurrentUser, db: Db, env: Env = "test", q: str | None = None,
                        limit: int = 25, offset: int = 0) -> dict[str, Any]:
    await _member(db, org_id, user)
    query = select(Subject).where(Subject.org_id == org_id, Subject.env == env)
    if q:
        query = query.where(Subject.customer_ref == q)
    rows = (await db.exec(query.order_by(Subject.created_at.desc()).offset(offset).limit(min(limit, 100)))).all()  # pyright: ignore[reportAttributeAccessIssue]
    return {"data": [await cs.serialize_subject(db, s) for s in rows], "limit": limit, "offset": offset}


@router.get("/organisations/{org_id}/users")
async def console_users(org_id: str, user: CurrentUser, db: Db, env: Env = "test", status: str | None = None,
                        q: str | None = None, limit: int = 25, offset: int = 0) -> dict[str, Any]:
    """Everyone this business verified in `env` (FOID account or not), with a derived status.
    `counts` ignores `status`/`q` (for the summary cards); `total` is after filtering."""
    await _member(db, org_id, user)
    every = await cv.rows(db, org_id, env)
    hits = [r for r in every if (not status or r.status == status) and (not q or r.matches(q))]
    limit = max(1, min(limit, 100))
    return {"data": [r.out() for r in hits[offset:offset + limit]], "total": len(hits),
            "limit": limit, "offset": offset, "counts": cv.counts(every)}


@router.get("/organisations/{org_id}/subjects/{subject_id}")
async def dash_subject(org_id: str, subject_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user)
    s = await db.get(Subject, subject_id)
    if s is None or s.org_id != org_id:
        raise ApiError(404, "subject_not_found", "No such subject")
    out = await cs.serialize_subject(db, s)
    scopes = await consent.granted_scopes(db, org_id, s.id)
    checks = (await db.exec(select(CheckResult).where(CheckResult.subject_id == s.id)
                            .order_by(CheckResult.created_at.desc()))).all()  # pyright: ignore[reportAttributeAccessIssue]
    out["checks"] = [cs.serialize_check(c) if consent.CHECK_SCOPES.get(c.type) in scopes
                     else {"id": c.id, "type": c.type, "status": c.status, "redacted": True,
                           "created_at": cs.iso(c.created_at)} for c in checks]
    return out


# ---------------------------------------------------------------------------
# Overview, usage, audit
# ---------------------------------------------------------------------------

@router.get("/organisations/{org_id}/overview")
async def overview(org_id: str, user: CurrentUser, db: Db, env: Env = "test") -> dict[str, Any]:
    await _member(db, org_id, user)
    usage = (await db.exec(select(UsageEvent).where(UsageEvent.org_id == org_id, UsageEvent.env == env))).all()
    return {**await cv.overview(db, org_id, env), "checks_run": dict(Counter(u.check_type for u in usage))}


@router.get("/organisations/{org_id}/usage")
async def usage(org_id: str, user: CurrentUser, db: Db, env: Env = "live", month: str | None = None) -> dict[str, Any]:
    """Billable usage per check type. `month` = YYYY-MM (default: all time)."""
    await _member(db, org_id, user)
    rows = (await db.exec(select(UsageEvent).where(UsageEvent.org_id == org_id, UsageEvent.env == env))).all()
    if month:
        rows = [u for u in rows if (cs.iso(u.created_at) or "").startswith(month)]
    return {"env": env, "month": month, "by_check": dict(Counter(u.check_type for u in rows)),
            "billable": sum(1 for u in rows if u.billable)}


@router.get("/organisations/{org_id}/audit-log")
async def audit_log(org_id: str, user: CurrentUser, db: Db, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    await _member(db, org_id, user, "admin")
    rows = (await db.exec(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.created_at.desc())  # pyright: ignore[reportAttributeAccessIssue]
                          .offset(offset).limit(min(limit, 200)))).all()
    return [{"id": a.id, "action": a.action, "actor_type": a.actor_type, "actor_id": a.actor_id,
             "target_type": a.target_type, "target_id": a.target_id, "meta": a.meta,
             "at": cs.iso(a.created_at)} for a in rows]

