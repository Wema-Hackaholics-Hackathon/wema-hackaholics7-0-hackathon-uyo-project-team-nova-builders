"""Business administration — Security settings, danger zone, team invites.

Business side (/api/v1/business/organisations/{org_id}/...)
  GET  /security                     {require_2fa, alert_on_key_create, ip_allowlist}            admin+
  PUT  /security                     same body                                                     admin+
  POST /api-keys/revoke-all          every live and test key stops working                         owner
  POST /deactivate                   {confirm_name} → console + API suspended, data deleted in 30 days   owner
  POST /reactivate                   within those 30 days                                          owner
  GET  /invites                      pending invites                                               admin+
  POST /invites                      {email, role} → email with a 7-day link                       admin+
  POST /invites/{id}/resend          new link, new 7 days                                          admin+
  DELETE /invites/{id}               link stops working                                            admin+

Invite link (/api/v1/console/invites/{token}) — no business login needed
  GET  /{token}                      who invited you, to what, and whether you already have an account
  POST /{token}/accept               signed in (console token for the invited email) → joins;
                                     no account yet → {first_name, last_name, password} creates it and joins
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db, get_settings
from app.core.api_errors import ApiError
from app.core.crypto import new_token, sha256_hex
from app.core.dependencies import require_verified_console_user
from app.core.security import decode_console_access_token, hash_password
from app.models import ApiKey, ConsoleUser, Organisation, OrgInvite, OrgMember, WebhookDelivery
from app.routers.business import _member  # pyright: ignore[reportPrivateUsage]
from app.routers.console_auth import TokenResponse, _issue_tokens, _password_rule  # pyright: ignore[reportPrivateUsage]
from app.services import checks_service as cs
from app.services import console_inbox, console_notify
from app.services.billing_service import PLANS
from app.utils.limiter import limiter

router = APIRouter(prefix="/business", tags=["business-admin"])
public = APIRouter(prefix="/console/invites", tags=["console-invites"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]
InviteRole = Literal["admin", "developer", "reviewer", "viewer"]
INVITE_TTL = timedelta(days=7)
RETENTION = timedelta(days=30)


async def _org(db: AsyncSession, org_id: str) -> Organisation:
    org = await db.get(Organisation, org_id)
    assert org is not None
    return org


# ── security settings ───────────────────────────────────────────────────────

class Security(BaseModel):
    require_2fa: bool
    alert_on_key_create: bool
    ip_allowlist: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("ip_allowlist")
    @classmethod
    def valid_ips(cls, v: list[str]) -> list[str]:
        out = []
        for item in (x.strip() for x in v if x.strip()):
            try:
                out.append(str(ipaddress.ip_network(item, strict=False)))
            except ValueError:
                raise ValueError(f"'{item}' isn't an IP address or range (e.g. 102.89.4.10 or 102.89.4.0/24)")
        return out


def _security(org: Organisation) -> dict[str, Any]:
    return {"require_2fa": org.require_2fa, "alert_on_key_create": org.alert_on_key_create, "ip_allowlist": org.ip_allowlist}


@router.get("/organisations/{org_id}/security")
async def get_security(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    return _security(await _org(db, org_id))


@router.put("/organisations/{org_id}/security")
async def put_security(org_id: str, body: Security, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    org = await _org(db, org_id)
    if body.require_2fa and user.totp_enabled_at is None:
        raise ApiError(409, "two_factor_needed_first", "Turn on two-step sign-in for your own account first (My account)")
    before = _security(org)
    org.require_2fa, org.alert_on_key_create, org.ip_allowlist = body.require_2fa, body.alert_on_key_create, body.ip_allowlist
    db.add(org)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="security.updated",
             meta={"before": before, "after": _security(org)})
    await db.commit()
    return _security(org)


# ── danger zone ─────────────────────────────────────────────────────────────

class Deactivate(BaseModel):
    confirm_name: str


@router.post("/organisations/{org_id}/api-keys/revoke-all")
async def revoke_all_keys(org_id: str, user: CurrentUser, db: Db) -> dict[str, int]:
    await _member(db, org_id, user, "owner")
    now = datetime.now(timezone.utc)
    keys = (await db.exec(select(ApiKey).where(ApiKey.org_id == org_id, col(ApiKey.revoked_at).is_(None)))).all()
    for k in keys:
        k.revoked_at = now
        db.add(k)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="api_key.revoked_all", meta={"count": len(keys)})
    await console_inbox.notify(db, org_id, "api_keys_revoked", "All API keys were revoked",
                               f"{user.first_name} {user.last_name} revoked {len(keys)} key(s). Integrations need new keys.",
                               link="/api-keys", min_role="developer", exclude=user.id)
    await db.commit()
    return {"revoked": len(keys)}


@router.post("/organisations/{org_id}/deactivate")
async def deactivate(org_id: str, body: Deactivate, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "owner")
    org = await _org(db, org_id)
    if body.confirm_name.strip() != org.name:
        raise ApiError(422, "confirmation_mismatch", "Type the business name exactly to confirm", "confirm_name")
    org.status, org.deactivated_at = "suspended", datetime.now(timezone.utc)
    for d in (await db.exec(select(WebhookDelivery).where(WebhookDelivery.org_id == org_id, WebhookDelivery.status == "pending"))).all():
        d.status, d.last_error = "cancelled", "organisation deactivated"
        db.add(d)
    db.add(org)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="organisation.deactivated")
    await console_inbox.notify(db, org_id, "org_deactivated", f"{org.name} was deactivated",
                               f"By {user.first_name} {user.last_name}. Data is deleted after 30 days unless an owner reactivates it.",
                               link="/settings", exclude=user.id)
    await db.commit()
    return {"status": org.status, "deactivated_at": cs.iso(org.deactivated_at),
            "delete_after": cs.iso(org.deactivated_at + RETENTION)}


@router.post("/organisations/{org_id}/reactivate")
async def reactivate(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "owner", allow_deactivated=True)
    org = await _org(db, org_id)
    if org.status == "active":
        return {"status": "active"}
    org.status, org.deactivated_at = "active", None
    db.add(org)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="organisation.reactivated")
    await console_inbox.notify(db, org_id, "org_reactivated", f"{org.name} is active again",
                               f"Reactivated by {user.first_name} {user.last_name}.", link="/", exclude=user.id)
    await db.commit()
    return {"status": "active"}


# ── invites (business side) ─────────────────────────────────────────────────

class InviteBody(BaseModel):
    email: EmailStr
    role: InviteRole


def _invite_out(i: OrgInvite) -> dict[str, Any]:
    return {"id": i.id, "email": i.email, "role": i.role, "expires_at": cs.iso(i.expires_at),
            "expired": (cs.as_utc(i.expires_at) or cs.utcnow()) < cs.utcnow(), "created_at": cs.iso(i.created_at)}


def _pending(org_id: str) -> Any:
    return select(OrgInvite).where(OrgInvite.org_id == org_id, col(OrgInvite.accepted_at).is_(None),
                                   col(OrgInvite.revoked_at).is_(None))


async def _new_link(i: OrgInvite) -> str:
    token = new_token("inv-", 24)
    i.token_hash, i.expires_at = sha256_hex(token), datetime.now(timezone.utc) + INVITE_TTL
    return f"{get_settings().CONSOLE_URL.rstrip('/')}/invite/{token}"


@router.get("/organisations/{org_id}/invites")
async def list_invites(org_id: str, user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    await _member(db, org_id, user, "admin")
    return [_invite_out(i) for i in (await db.exec(_pending(org_id).order_by(col(OrgInvite.created_at).desc()))).all()]


@router.post("/organisations/{org_id}/invites", status_code=201)
async def create_invite(org_id: str, body: InviteBody, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    org = await _org(db, org_id)
    email = str(body.email).lower()
    already = (await db.exec(select(OrgMember).join(ConsoleUser, col(ConsoleUser.id) == OrgMember.console_user_id)
                             .where(OrgMember.org_id == org_id, ConsoleUser.email == email))).first()
    if already:
        raise ApiError(409, "already_member", "That person is already on the team")
    seats = PLANS[org.plan_code]["seats"]
    if seats is not None:
        members = (await db.exec(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org_id))).one()
        pending = (await db.exec(select(func.count()).select_from(_pending(org_id).subquery()))).one()
        if members + pending >= seats:
            raise ApiError(403, "seat_limit", f"Your {PLANS[org.plan_code]['name']} plan has {seats} seats — upgrade in Usage & Billing")
    for old in (await db.exec(_pending(org_id).where(OrgInvite.email == email))).all():
        old.revoked_at = datetime.now(timezone.utc)       # one live invite per email
        db.add(old)
    inv = OrgInvite(org_id=org_id, email=email, role=body.role, token_hash="", invited_by=user.id,
                    expires_at=datetime.now(timezone.utc))
    link = await _new_link(inv)
    db.add(inv)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="member.invited",
             target_type="invite", target_id=inv.id, meta={"email": email, "role": body.role})
    await db.commit()
    await console_notify.invite(to=email, org=org, inviter=user, role=body.role, link=link)
    return _invite_out(inv)


async def _invite(db: AsyncSession, org_id: str, invite_id: str) -> OrgInvite:
    i = await db.get(OrgInvite, invite_id)
    if i is None or i.org_id != org_id or i.accepted_at or i.revoked_at:
        raise ApiError(404, "invite_not_found", "No such pending invite")
    return i


@router.post("/organisations/{org_id}/invites/{invite_id}/resend")
async def resend_invite(org_id: str, invite_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    i = await _invite(db, org_id, invite_id)
    link = await _new_link(i)        # the old link stops working
    db.add(i)
    await db.commit()
    await console_notify.invite(to=i.email, org=await _org(db, org_id), inviter=user, role=i.role, link=link)
    return _invite_out(i)


@router.delete("/organisations/{org_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(org_id: str, invite_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "admin")
    i = await _invite(db, org_id, invite_id)
    i.revoked_at = datetime.now(timezone.utc)
    db.add(i)
    await db.commit()


# ── invites (the person invited) ────────────────────────────────────────────

class AcceptBody(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name: str | None = Field(default=None, min_length=1, max_length=60)
    password: str | None = None


_optional_bearer = HTTPBearer(auto_error=False)


async def _usable(db: AsyncSession, token: str) -> tuple[OrgInvite, Organisation]:
    i = (await db.exec(select(OrgInvite).where(OrgInvite.token_hash == sha256_hex(token)))).first()
    if i is None or i.revoked_at:
        raise ApiError(404, "invite_not_found", "This invite link isn't valid — ask for a new one")
    if i.accepted_at:
        raise ApiError(410, "invite_used", "This invite has already been accepted — sign in instead")
    if (cs.as_utc(i.expires_at) or cs.utcnow()) < cs.utcnow():
        raise ApiError(410, "invite_expired", "This invite has expired — ask for a new one")
    org = await _org(db, i.org_id)
    if org.status != "active":
        raise ApiError(410, "organisation_deactivated", "This business is no longer active")
    return i, org


@public.get("/{token}")
async def invite_info(token: str, db: Db) -> dict[str, Any]:
    i, org = await _usable(db, token)
    inviter = await db.get(ConsoleUser, i.invited_by) if i.invited_by else None
    has_account = (await db.exec(select(ConsoleUser.id).where(ConsoleUser.email == i.email))).first() is not None
    return {"org_name": org.name, "role": i.role, "email": i.email, "has_account": has_account,
            "invited_by": f"{inviter.first_name} {inviter.last_name}" if inviter else None, "expires_at": cs.iso(i.expires_at)}


@public.post("/{token}/accept")
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def accept_invite(
    request: Request,  # required by slowapi
    token: str,
    body: AcceptBody,
    db: Db,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)],
) -> dict[str, Any]:
    i, org = await _usable(db, token)
    member = (await db.exec(select(ConsoleUser).where(ConsoleUser.email == i.email))).first()
    tokens: TokenResponse | None = None
    created = member is None
    if member is not None:
        # Existing account: must be signed in as that account
        try:
            signed_in = decode_console_access_token(creds.credentials) if creds else None
        except JWTError:
            signed_in = None
        if signed_in != member.id:
            raise ApiError(401, "sign_in_required", f"Sign in as {i.email} to accept this invite")
    else:
        if not (body.first_name and body.last_name and body.password):
            raise ApiError(422, "account_details_required", "Enter your name and a password to create your console account")
        try:
            _password_rule(body.password)
        except ValueError as exc:
            raise ApiError(422, "weak_password", str(exc), "password")
        # The emailed link proves the address, so the account starts verified.
        member = ConsoleUser(first_name=body.first_name.strip(), last_name=body.last_name.strip(), email=i.email,
                             hashed_password=hash_password(body.password), email_verified_at=datetime.now(timezone.utc))
        db.add(member)
        await db.flush()
    if not (await db.exec(select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.console_user_id == member.id))).first():
        db.add(OrgMember(org_id=org.id, console_user_id=member.id, role=i.role))
    i.accepted_at = datetime.now(timezone.utc)
    db.add(i)
    cs.audit(db, org_id=org.id, actor_type="member", actor_id=member.id, action="member.added",
             target_type="member", target_id=member.id, meta={"role": i.role, "via": "invite"})
    await console_inbox.notify(db, org.id, "member_joined", f"{member.first_name} {member.last_name} joined the team",
                               f"{member.email} accepted the invite as {i.role}.", link="/team", min_role="admin", exclude=member.id)
    if created:
        tokens = await _issue_tokens(db, member)     # commits; signs the new account in
    else:
        await db.commit()
    return {"org_id": org.id, "org_name": org.name, "role": i.role, **(tokens.model_dump() if tokens else {})}
