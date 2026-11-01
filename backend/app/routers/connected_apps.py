"""Connected apps — a FOID user's view of businesses that hold their data.

/api/v1/connected-apps (FOID user JWT)

Lists every organisation with a consent grant on a subject linked to this user
(including businesses that verified them before they joined FOID), what each
can see, and lets the user revoke. Revoking stops all data flow to that business
immediately (see services/consent_service.revoke_subject).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.dependencies import get_current_user
from app.models import CheckResult, ConsentGrant, Organisation, Subject, User
from app.services import checks_service as cs
from app.services import consent_service as consent

router = APIRouter(prefix="/connected-apps", tags=["connected-apps"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


async def _apps(db: AsyncSession, user: User, org_id: str | None = None) -> list[dict[str, Any]]:
    q = select(Subject).where(Subject.user_id == user.id)
    if org_id:
        q = q.where(Subject.org_id == org_id)
    subjects = (await db.exec(q)).all()
    by_org: dict[str, dict[str, Any]] = {}
    for s in subjects:
        org = await db.get(Organisation, s.org_id)
        if org is None:
            continue
        grants = (await db.exec(select(ConsentGrant).where(ConsentGrant.subject_id == s.id)
                                .order_by(ConsentGrant.granted_at))).all()  # pyright: ignore[reportArgumentType]
        checks = (await db.exec(select(CheckResult).where(CheckResult.subject_id == s.id)
                                .order_by(CheckResult.created_at.desc()))).all()  # pyright: ignore[reportAttributeAccessIssue]
        app = by_org.setdefault(f"{org.id}:{s.env}", {
            "org_id": org.id,
            "sandbox": s.env == "test",
            "name": org.name,
            "logo_url": org.logo_url,
            "website": org.website,
            "status": "revoked",
            "scopes": set(),
            "first_connected_at": None,
            "verified_before_joining_foid": False,
            "grants": [],
            "checks": [],
        })
        for g in grants:
            if g.status == "active":
                app["status"] = "active"
                app["scopes"].update(g.scopes)
            app["grants"].append({
                "id": g.id, "scopes": g.scopes, "purpose": g.purpose, "source": g.source, "status": g.status,
                "granted_at": cs.iso(g.granted_at), "revoked_at": cs.iso(g.revoked_at), "revoked_by": g.revoked_by,
            })
            first = app["first_connected_at"]
            if first is None or (cs.iso(g.granted_at) or "") < first:
                app["first_connected_at"] = cs.iso(g.granted_at)
        app["verified_before_joining_foid"] |= s.link_method in ("email_nin", "face_nin")
        app["checks"].extend({"type": c.type, "status": c.status, "at": cs.iso(c.created_at)} for c in checks)
    out = []
    for app in by_org.values():
        app["scopes"] = [{"scope": sc, "description": consent.SCOPES.get(sc, sc)} for sc in sorted(app["scopes"])]
        out.append(app)
    return sorted(out, key=lambda a: (a["status"] != "active", a["name"].lower()))


@router.get("")
async def list_connected_apps(user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    return await _apps(db, user)


@router.get("/{org_id}")
async def get_connected_app(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    apps = await _apps(db, user, org_id)
    if not apps:
        raise ApiError(404, "connected_app_not_found", "That business has no connection to your account")
    return apps[0]


@router.delete("/{org_id}")
async def revoke_connected_app(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Revoke everything this business can access. It is notified once and gets nothing more."""
    subjects = (await db.exec(select(Subject).where(Subject.user_id == user.id, Subject.org_id == org_id))).all()
    if not subjects:
        raise ApiError(404, "connected_app_not_found", "That business has no connection to your account")
    revoked = 0
    for s in subjects:
        revoked += await consent.revoke_subject(db, org_id=org_id, subject=s, by="user", actor_id=user.id)
    await db.commit()
    return {"org_id": org_id, "revoked_grants": revoked, "status": "revoked"}
