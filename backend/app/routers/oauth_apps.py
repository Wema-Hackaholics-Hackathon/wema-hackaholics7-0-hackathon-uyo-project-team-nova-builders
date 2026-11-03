"""Console: 'Continue with FOID' sign-in apps — /api/v1/business/organisations/{org_id}/apps

GET    /apps?env=                        list (with usable secrets' hints)
POST   /apps                             {env, name, origins, redirect_uris, scopes} → app + client secret (ONCE)
PATCH  /apps/{app_id}                    {name?, origins?, redirect_uris?, scopes?, auth_method?, public_jwk?}
POST   /apps/{app_id}/secrets            new secret (ONCE); older secrets keep working 24 h, then stop
DELETE /apps/{app_id}/secrets/{id}       revoke a secret now
DELETE /apps/{app_id}                    delete the app: sign-in stops, secrets revoked

Developer role or higher. Live apps need an approved KYB (like live API keys).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.dependencies import require_verified_console_user
from app.models import ConsoleUser, OAuthApp, OAuthClientSecret, Organisation
from app.routers.business import _member
from app.services import checks_service as cs
from app.services import console_inbox, console_notify
from app.services import oauth_apps as oa

router = APIRouter(prefix="/business", tags=["business-console"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]
Env = Literal["test", "live"]


class AppCreate(BaseModel):
    env: Env
    name: str = Field(min_length=2, max_length=60)
    origins: list[str] = Field(default_factory=list)
    redirect_uris: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["profile"])


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    origins: list[str] | None = None
    redirect_uris: list[str] | None = None
    scopes: list[str] | None = None
    auth_method: Literal["client_secret", "private_key_jwt"] | None = None
    public_jwk: dict[str, Any] | None = None


async def _app(db: AsyncSession, org_id: str, app_id: str) -> OAuthApp:
    app = await db.get(OAuthApp, app_id)
    if app is None or app.org_id != org_id or app.disabled_at is not None:
        raise ApiError(404, "app_not_found", "No such sign-in app")
    return app


async def _secrets(db: AsyncSession, app_id: str) -> list[OAuthClientSecret]:
    return list((await db.exec(select(OAuthClientSecret).where(OAuthClientSecret.app_id == app_id))).all())


async def _out(db: AsyncSession, app: OAuthApp) -> dict[str, Any]:
    return oa.app_out(app, await _secrets(db, app.id))


async def _issue_secret(db: AsyncSession, org: Organisation, app: OAuthApp, user: ConsoleUser) -> tuple[str, OAuthClientSecret]:
    raw, hint, h = oa.new_secret(app.env)
    s = OAuthClientSecret(app_id=app.id, hint=hint, secret_hash=h, created_by=user.id)
    db.add(s)
    await console_inbox.notify(db, org.id, "api_key_created", f"New {app.env} client secret: {app.name}",
                               f"{user.first_name} {user.last_name} created {hint}.", link="/apps",
                               min_role="admin", exclude=user.id)
    return raw, s


@router.get("/organisations/{org_id}/apps")
async def list_apps(org_id: str, user: CurrentUser, db: Db, env: Env | None = None) -> list[dict[str, Any]]:
    await _member(db, org_id, user, "developer")
    q = select(OAuthApp).where(OAuthApp.org_id == org_id, OAuthApp.disabled_at == None)  # noqa: E711
    if env:
        q = q.where(OAuthApp.env == env)
    return [await _out(db, a) for a in (await db.exec(q.order_by(col(OAuthApp.created_at)))).all()]


@router.get("/oauth-scopes")
async def oauth_scopes() -> dict[str, str]:
    return oa.APP_SCOPES


@router.post("/organisations/{org_id}/apps", status_code=201)
async def create_app(org_id: str, body: AppCreate, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "developer")
    org = await db.get(Organisation, org_id)
    assert org is not None
    if body.env == "live" and not org.live_enabled:
        raise ApiError(403, "live_mode_disabled", "Complete business verification (KYB) to create live apps")
    count = len((await db.exec(select(OAuthApp.id).where(OAuthApp.org_id == org_id, OAuthApp.env == body.env,
                                                         OAuthApp.disabled_at == None))).all())  # noqa: E711
    if count >= oa.MAX_APPS_PER_ENV:
        raise ApiError(409, "app_limit", f"Up to {oa.MAX_APPS_PER_ENV} {body.env} apps per business — delete one first")
    redirects = oa.clean_list(body.env, body.redirect_uris, "redirect_uris")
    origins = oa.clean_list(body.env, body.origins, "origins")
    if body.env == "live" and not (redirects or origins):
        raise ApiError(422, "invalid_app_config", "Add at least one https origin or redirect URI", param="origins")
    app = OAuthApp(org_id=org_id, env=body.env, name=body.name.strip(), client_id=oa.new_client_id(body.env),
                   origins=origins, redirect_uris=redirects, scopes=oa.clean_scopes(body.scopes), created_by=user.id)
    db.add(app)
    raw, s = await _issue_secret(db, org, app, user)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="oauth_app.created",
             target_type="oauth_app", target_id=app.id, meta={"env": app.env, "client_id": app.client_id})
    await db.commit()
    await console_notify.credential_created(db, org, user, env=app.env, name=app.name, hint=s.hint,
                                            what="client secret", where="Sign-in apps")
    return {**await _out(db, app), "client_secret": raw}


@router.patch("/organisations/{org_id}/apps/{app_id}")
async def update_app(org_id: str, app_id: str, body: AppUpdate, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "developer")
    app = await _app(db, org_id, app_id)
    if body.name is not None:
        app.name = body.name.strip()
    if body.origins is not None:
        app.origins = oa.clean_list(app.env, body.origins, "origins")
    if body.redirect_uris is not None:
        app.redirect_uris = oa.clean_list(app.env, body.redirect_uris, "redirect_uris")
    if body.scopes is not None:
        app.scopes = oa.clean_scopes(body.scopes)
    if body.public_jwk is not None:
        app.public_jwk = oa.clean_public_jwk(body.public_jwk)
    if body.auth_method is not None:
        if body.auth_method == "private_key_jwt" and not app.public_jwk:
            raise ApiError(422, "invalid_app_config", "Add your public key first", param="public_jwk")
        app.auth_method = body.auth_method
    if app.env == "live" and not (app.origins or app.redirect_uris):
        raise ApiError(422, "invalid_app_config", "A live app needs at least one https origin or redirect URI", param="origins")
    db.add(app)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="oauth_app.updated",
             target_type="oauth_app", target_id=app.id,
             meta={k: v for k, v in body.model_dump(exclude_none=True).items() if k != "public_jwk"})
    await db.commit()
    return await _out(db, app)


@router.post("/organisations/{org_id}/apps/{app_id}/secrets", status_code=201)
async def rotate_secret(org_id: str, app_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    """New secret, shown once. Secrets that were working keep working for 24 h so you can redeploy."""
    await _member(db, org_id, user, "developer")
    app = await _app(db, org_id, app_id)
    org = await db.get(Organisation, org_id)
    assert org is not None
    now = datetime.now(timezone.utc)
    grace = now + timedelta(hours=oa.ROTATION_OVERLAP_HOURS)
    for old in await _secrets(db, app.id):
        if oa.secret_usable(old, now) and (old.expires_at is None or old.expires_at > grace):
            old.expires_at = grace
            db.add(old)
    raw, s = await _issue_secret(db, org, app, user)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="oauth_app.secret_rotated",
             target_type="oauth_app", target_id=app.id)
    await db.commit()
    await console_notify.credential_created(db, org, user, env=app.env, name=app.name, hint=s.hint,
                                            what="client secret", where="Sign-in apps")
    return {**await _out(db, app), "client_secret": raw}


@router.delete("/organisations/{org_id}/apps/{app_id}/secrets/{secret_id}", status_code=204)
async def revoke_secret(org_id: str, app_id: str, secret_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "developer")
    app = await _app(db, org_id, app_id)
    s = await db.get(OAuthClientSecret, secret_id)
    if s is None or s.app_id != app.id:
        raise ApiError(404, "secret_not_found", "No such client secret")
    if s.revoked_at is None:
        s.revoked_at = datetime.now(timezone.utc)
        db.add(s)
        cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="oauth_app.secret_revoked",
                 target_type="oauth_app", target_id=app.id)
        await db.commit()


@router.delete("/organisations/{org_id}/apps/{app_id}", status_code=204)
async def delete_app(org_id: str, app_id: str, user: CurrentUser, db: Db) -> None:
    """Sign-in with this client id stops at once. People's existing consent grants are kept (they can revoke)."""
    await _member(db, org_id, user, "developer")
    app = await _app(db, org_id, app_id)
    now = datetime.now(timezone.utc)
    app.disabled_at = now
    db.add(app)
    for s in await _secrets(db, app.id):
        if s.revoked_at is None:
            s.revoked_at = now
            db.add(s)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="oauth_app.deleted",
             target_type="oauth_app", target_id=app.id)
    await db.commit()
