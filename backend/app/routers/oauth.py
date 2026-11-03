"""'Continue with FOID' — the popup's API (/api/v1/oauth). The popup is the FOID user app at /oauth/authorize.

POST /authorize                         validate the business's request → request id + what to show
GET  /requests/{id}                      current state (reloads)
POST /requests/{id}/email                {email} → one-time code by email
POST /requests/{id}/email/verify         {code, device_id?} → FOID tokens | {mfa_required, mfa_token} | {guest_ticket}
GET  /requests/{id}/review               (FOID user) what's missing, face re-match needed?
POST /requests/{id}/approve              (FOID user) → {payload: {code, state}, origin | redirect_url}
POST /requests/{id}/deny                 → {payload: {error: access_denied, state}, …}
POST /requests/{id}/guest/start|status|finish|save   new person (guest ticket): hosted verification, Save to FOID

The token exchange is on the Open API: routers/oauth_token.py.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_ticket
from app.models import User
from app.services import oauth_flow as of
from app.services.user_signin import complete_sign_in
from app.utils.limiter import limiter

router = APIRouter(prefix="/oauth", tags=["continue-with-foid"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class AuthorizeBody(BaseModel):
    client_id: str = Field(max_length=100)
    response_mode: Literal["web_message", "query"] = "web_message"
    origin: str | None = Field(default=None, max_length=300)
    redirect_uri: str | None = Field(default=None, max_length=2000)
    scope: str = Field(default="profile", max_length=300)
    state: str = Field(max_length=512)
    nonce: str | None = Field(default=None, max_length=512)
    code_challenge: str = Field(max_length=200)
    code_challenge_method: str = "S256"


class EmailBody(BaseModel):
    email: EmailStr


class CodeBody(BaseModel):
    code: str = Field(max_length=12)
    device_id: str | None = Field(default=None, max_length=100)


class TicketBody(BaseModel):
    ticket: str
    device_id: str | None = Field(default=None, max_length=100)


class GuestStartBody(TicketBody):
    """Name exactly as on the NIN (the check matches against it) and, optionally, date of birth."""
    first_name: str = Field(min_length=1, max_length=60)
    middle_name: str | None = Field(default=None, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    date_of_birth: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/authorize")
@limiter.limit("30/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def authorize(request: Request, body: AuthorizeBody, db: Db) -> dict[str, Any]:
    req = await of.start(db, **body.model_dump())
    await db.commit()
    req, app = await of.load(db, req.id)
    return await of.view(db, req, app)


@router.get("/requests/{request_id}")
async def get_request(request_id: str, db: Db) -> dict[str, Any]:
    req, app = await of.load(db, request_id, open_only=False)
    return await of.view(db, req, app)


@router.post("/requests/{request_id}/email")
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def send_code(request: Request, request_id: str, body: EmailBody, db: Db) -> dict[str, str]:
    req, app = await of.load(db, request_id)
    await of.send_otp(db, req, app, str(body.email))
    return {"sent_to": req.email or ""}


@router.post("/requests/{request_id}/email/verify")
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def verify_code(request: Request, request_id: str, body: CodeBody, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    user = await of.check_otp(db, req, body.code)
    if user is None:
        await db.commit()
        return {"account": False, "guest_ticket": of.guest_ticket(req)}
    if user.totp_enabled_at is not None:   # the email code replaces the password, not the second factor
        await db.commit()
        return {"account": True, "mfa_required": True, "mfa_token": create_ticket(user.id, "user_mfa")}
    access, refresh = await complete_sign_in(db, user, request, body.device_id)
    return {"account": True, "access_token": access, "refresh_token": refresh}


@router.get("/requests/{request_id}/review")
async def review(request_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    return {**await of.review(db, req, user),
            "person": {"first_name": user.first_name, "last_name": user.last_name, "email": user.email}}


@router.post("/requests/{request_id}/approve")
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def approve(request: Request, request_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    return await of.approve_user(db, req, user, request)


@router.post("/requests/{request_id}/deny")
async def deny(request_id: str, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    return await of.deny(db, req)


@router.post("/requests/{request_id}/guest/start")
async def guest_start(request_id: str, body: GuestStartBody, db: Db) -> dict[str, str]:
    req, _ = await of.load(db, request_id)
    of.check_guest_ticket(req, body.ticket)
    return {"hosted_url": await of.guest_start(db, req, first_name=body.first_name, last_name=body.last_name,
                                               middle_name=body.middle_name, date_of_birth=body.date_of_birth)}


@router.post("/requests/{request_id}/guest/status")
async def guest_status(request_id: str, body: TicketBody, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    of.check_guest_ticket(req, body.ticket)
    return await of.guest_status(db, req)


@router.post("/requests/{request_id}/guest/save")
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def guest_save(request: Request, request_id: str, body: TicketBody, db: Db) -> dict[str, Any]:
    """The explicit 'Save this to FOID' tap. Signs the person in to their new account."""
    req, _ = await of.load(db, request_id)
    of.check_guest_ticket(req, body.ticket)
    user = await of.save_to_foid(db, req)
    access, refresh = await complete_sign_in(db, user, request, body.device_id)
    return {"access_token": access, "refresh_token": refresh}


@router.post("/requests/{request_id}/guest/finish")
async def guest_finish(request_id: str, body: TicketBody, db: Db) -> dict[str, Any]:
    req, _ = await of.load(db, request_id)
    of.check_guest_ticket(req, body.ticket)
    return await of.guest_finish(db, req)
