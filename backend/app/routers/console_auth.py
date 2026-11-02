"""Business console accounts — /api/v1/console/auth/*

Separate from FOID user auth (/auth/*): own table (console_users), own refresh
tokens, and access tokens of type "console" that the user app rejects (and user
tokens are rejected here). The same email may hold both a FOID user account and
a console account; they share nothing.

POST /signup               {first_name, last_name, email, password, company_name} → tokens; creates the org (owner)
POST /login                {email, password} → tokens, or {mfa_required, mfa_token} when two-step sign-in is on
POST /login/2fa            {mfa_token, code} → tokens
POST /refresh              {refresh_token} → new tokens (rotation)
POST /logout               {refresh_token} → 204
GET  /me                   the signed-in console account
POST /verify-email         {code} (signed in)
POST /resend-verification (signed in)
POST /forgot-password      {email} → 200 always
POST /reset-password       {email, code, new_password} → 204, signs out everywhere
PATCH /me                  {first_name?, last_name?}
POST /me/password          {current_password, new_password} → new tokens; other sessions signed out
POST /me/2fa/setup         → {secret, otpauth_uri} (not active until confirmed)
POST /me/2fa/enable        {code}
POST /me/2fa/disable       {password, code}
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from jose import JWTError

from app.config import get_db
from app.core import totp
from app.core.crypto import decrypt_str, encrypt_str
from app.core.dependencies import get_console_user
from app.core.security import (
    create_console_access_token,
    decode_console_access_token,
    create_refresh_token_expiry,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import ConsoleOtp, ConsoleRefreshToken, ConsoleUser, Organisation, OrgMember
from app.routers.business import new_organisation
from app.services.email_service import send_email
from app.services.email_templates import console_code
from app.utils.limiter import limiter

router = APIRouter(prefix="/console/auth", tags=["console-auth"])
Db = Annotated[AsyncSession, Depends(get_db)]
Member = Annotated[ConsoleUser, Depends(get_console_user)]

_OTP_TTL = {"verify_email": timedelta(minutes=30), "reset_password": timedelta(minutes=10)}
_MAX_OTP_ATTEMPTS = 5


def _password_rule(v: str) -> str:
    missing = [label for ok, label in (
        (len(v) >= 8, "at least 8 characters"), (re.search(r"[A-Z]", v), "one uppercase letter"),
        (re.search(r"[a-z]", v), "one lowercase letter"), (re.search(r"[0-9]", v), "one number"),
        (re.search(r"[^A-Za-z0-9]", v), "one special character")) if not ok]
    if missing:
        raise ValueError(f"password must contain: {', '.join(missing)}")
    return v


class SignupBody(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str
    company_name: str = Field(min_length=2, max_length=120)

    @field_validator("first_name", "last_name", "company_name")
    @classmethod
    def strip(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _password_rule(v)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TokenBody(BaseModel):
    refresh_token: str


class CodeBody(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class EmailBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _password_rule(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None


class MfaBody(BaseModel):
    mfa_token: str
    code: str


class ProfileBody(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name: str | None = Field(default=None, min_length=1, max_length=60)


class PasswordBody(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _password_rule(v)


class DisableBody(BaseModel):
    password: str
    code: str


class ConsoleMe(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    email_verified: bool
    two_factor_enabled: bool
    created_at: datetime


# ── helpers ─────────────────────────────────────────────────────────────────

async def _issue_tokens(db: AsyncSession, member: ConsoleUser) -> TokenResponse:
    raw = generate_refresh_token()
    db.add(ConsoleRefreshToken(console_user_id=member.id, token_hash=hash_refresh_token(raw),
                               expires_at=create_refresh_token_expiry()))
    await db.commit()
    return TokenResponse(access_token=create_console_access_token(member.id), refresh_token=raw)


async def _stage_otp(db: AsyncSession, member: ConsoleUser, purpose: str) -> str:
    """Burn older unused codes for this purpose and stage a new one. Caller commits, then emails."""
    for old in (await db.exec(select(ConsoleOtp).where(
            ConsoleOtp.console_user_id == member.id, ConsoleOtp.purpose == purpose,
            ConsoleOtp.used == False))).all():  # noqa: E712
        old.used = True
        db.add(old)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(ConsoleOtp(console_user_id=member.id, purpose=purpose, code_hash=hash_refresh_token(code),
                      expires_at=datetime.now(timezone.utc) + _OTP_TTL[purpose]))
    return code


async def _email_otp(member: ConsoleUser, code: str, purpose: str) -> None:
    subject, html = console_code(first_name=member.first_name, otp=code, to=member.email, purpose=purpose)
    await send_email(to=member.email, subject=subject, html=html,
                     body=f"Hi {member.first_name},\n\nYour FOID Console code is: {code}\n\n— FOID")


async def _use_otp(db: AsyncSession, member: ConsoleUser, purpose: str, code: str) -> None:
    """Check a code (max 5 tries per code). Raises 400 on any failure; marks it used on success."""
    otp = (await db.exec(select(ConsoleOtp).where(
        ConsoleOtp.console_user_id == member.id, ConsoleOtp.purpose == purpose,
        ConsoleOtp.used == False).order_by(ConsoleOtp.created_at.desc()))).first()  # noqa: E712  # pyright: ignore[reportAttributeAccessIssue]
    bad = HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has expired — request a new one")
    if otp is None or otp.expires_at < datetime.now(timezone.utc) or otp.attempts >= _MAX_OTP_ATTEMPTS:
        raise bad
    if not secrets.compare_digest(otp.code_hash, hash_refresh_token(code)):
        otp.attempts += 1
        db.add(otp)
        await db.commit()
        raise bad
    otp.used = True
    db.add(otp)


def _me(member: ConsoleUser) -> ConsoleMe:
    return ConsoleMe(id=member.id, first_name=member.first_name, last_name=member.last_name, email=member.email,
                     email_verified=member.email_verified_at is not None,
                     two_factor_enabled=member.totp_enabled_at is not None, created_at=member.created_at)


def _check_code(member: ConsoleUser, code: str) -> None:
    """Accept a 2FA code once (replay-safe). Caller commits."""
    if not member.totp_secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-step sign-in isn't set up")
    step = totp.verify(decrypt_str(member.totp_secret_enc), code, member.totp_last_step)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has already been used — try the next one")
    member.totp_last_step = step


async def _revoke_sessions(db: AsyncSession, member: ConsoleUser) -> None:
    for t in (await db.exec(select(ConsoleRefreshToken).where(
            ConsoleRefreshToken.console_user_id == member.id, ConsoleRefreshToken.revoked == False))).all():  # noqa: E712
        t.revoked = True
        db.add(t)


async def _by_email(db: AsyncSession, email: str) -> ConsoleUser | None:
    return (await db.exec(select(ConsoleUser).where(ConsoleUser.email == email.lower()))).first()


# ── routes ──────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def signup(request: Request, body: SignupBody, db: Db) -> TokenResponse:  # request: required by slowapi
    if await _by_email(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A console account with this email already exists")
    member = ConsoleUser(first_name=body.first_name, last_name=body.last_name, email=body.email.lower(),
                         hashed_password=hash_password(body.password))
    db.add(member)
    await db.flush()
    await new_organisation(db, member, body.company_name)
    code = await _stage_otp(db, member, "verify_email")
    tokens = await _issue_tokens(db, member)   # commits everything above
    await _email_otp(member, code, "verify_email")
    return tokens


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def login(request: Request, body: LoginBody, db: Db) -> LoginResponse:  # request: required by slowapi
    member = await _by_email(db, body.email)
    # Same product decision as the user app: say which part is wrong (rate limit is the mitigation).
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No console account exists with this email address")
    if not verify_password(body.password, member.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")
    if member.totp_enabled_at is not None:   # password was right; now the authenticator code
        return LoginResponse(mfa_required=True, mfa_token=create_console_access_token(member.id, "console_mfa", minutes=5))
    t = await _issue_tokens(db, member)
    return LoginResponse(access_token=t.access_token, refresh_token=t.refresh_token)


@router.post("/login/2fa", response_model=TokenResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def login_2fa(request: Request, body: MfaBody, db: Db) -> TokenResponse:  # request: required by slowapi
    try:
        member_id = decode_console_access_token(body.mfa_token, "console_mfa")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired — enter your password again")
    member = await db.get(ConsoleUser, member_id)
    if member is None or member.totp_enabled_at is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired — enter your password again")
    _check_code(member, body.code)
    db.add(member)
    return await _issue_tokens(db, member)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def refresh(request: Request, body: TokenBody, db: Db) -> TokenResponse:  # request: required by slowapi
    row = (await db.exec(select(ConsoleRefreshToken).where(
        ConsoleRefreshToken.token_hash == hash_refresh_token(body.refresh_token)))).first()
    if row is None or row.revoked or row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked refresh token")
    member = await db.get(ConsoleUser, row.console_user_id)
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked refresh token")
    row.revoked = True
    db.add(row)
    return await _issue_tokens(db, member)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: TokenBody, db: Db) -> None:
    row = (await db.exec(select(ConsoleRefreshToken).where(
        ConsoleRefreshToken.token_hash == hash_refresh_token(body.refresh_token)))).first()
    if row and not row.revoked:
        row.revoked = True
        db.add(row)
        await db.commit()


@router.get("/me", response_model=ConsoleMe)
async def me(member: Member) -> ConsoleMe:
    return _me(member)


@router.post("/verify-email", response_model=ConsoleMe)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def verify_email(request: Request, body: CodeBody, member: Member, db: Db) -> ConsoleMe:  # request: slowapi
    if member.email_verified_at is None:
        await _use_otp(db, member, "verify_email", body.code)
        member.email_verified_at = datetime.now(timezone.utc)
        db.add(member)
        await db.commit()
        await db.refresh(member)
    return _me(member)


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def resend_verification(request: Request, member: Member, db: Db) -> dict[str, str]:  # request: slowapi
    if member.email_verified_at is None:
        code = await _stage_otp(db, member, "verify_email")
        await db.commit()
        await _email_otp(member, code, "verify_email")
    return {"message": "If your email isn't verified yet, a new code is on its way"}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def forgot_password(request: Request, body: EmailBody, db: Db) -> dict[str, str]:  # request: slowapi
    member = await _by_email(db, body.email)
    if member is not None:
        code = await _stage_otp(db, member, "reset_password")
        await db.commit()
        await _email_otp(member, code, "reset_password")
    return {"message": "If a console account uses that email, a reset code is on its way"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def reset_password(request: Request, body: ResetBody, db: Db) -> None:  # request: slowapi
    member = await _by_email(db, body.email)
    if member is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has expired — request a new one")
    await _use_otp(db, member, "reset_password", body.code)
    member.hashed_password = hash_password(body.new_password)
    db.add(member)
    await _revoke_sessions(db, member)   # sign out every session
    await db.commit()


@router.patch("/me", response_model=ConsoleMe)
async def update_me(body: ProfileBody, member: Member, db: Db) -> ConsoleMe:
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(member, k, v.strip())
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return _me(member)


@router.post("/me/password", response_model=TokenResponse)
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def change_password(request: Request, body: PasswordBody, member: Member, db: Db) -> TokenResponse:  # request: slowapi
    if not verify_password(body.current_password, member.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is wrong")
    member.hashed_password = hash_password(body.new_password)
    db.add(member)
    await _revoke_sessions(db, member)          # other devices are signed out; this one gets fresh tokens
    return await _issue_tokens(db, member)


@router.post("/me/2fa/setup")
async def setup_2fa(member: Member, db: Db) -> dict[str, str]:
    if member.totp_enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on")
    secret = totp.new_secret()
    member.totp_secret_enc, member.totp_last_step = encrypt_str(secret), None
    db.add(member)
    await db.commit()
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, member.email)}


@router.post("/me/2fa/enable", response_model=ConsoleMe)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def enable_2fa(request: Request, body: CodeBody, member: Member, db: Db) -> ConsoleMe:  # request: slowapi
    if member.totp_enabled_at is not None:
        return _me(member)
    _check_code(member, body.code)
    member.totp_enabled_at = datetime.now(timezone.utc)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return _me(member)


@router.post("/me/2fa/disable", response_model=ConsoleMe)
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def disable_2fa(request: Request, body: DisableBody, member: Member, db: Db) -> ConsoleMe:  # request: slowapi
    if member.totp_enabled_at is None:
        return _me(member)
    if not verify_password(body.password, member.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is wrong")
    _check_code(member, body.code)
    needs = (await db.exec(select(Organisation.name).join(OrgMember, OrgMember.org_id == Organisation.id)  # pyright: ignore[reportArgumentType]
                           .where(OrgMember.console_user_id == member.id, Organisation.require_2fa == True))).all()  # noqa: E712
    if needs:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{', '.join(needs)} require two-step sign-in — it can't be turned off")
    member.totp_secret_enc = member.totp_enabled_at = member.totp_last_step = None
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return _me(member)
