"""Sign-in security for FOID user accounts (Settings → Security).

/api/v1/auth/...
  POST   /login/2fa                 {mfa_token, code, device_id?} → tokens (after /login said mfa_required)
  GET    /me/security               → two_factor_enabled, login_alerts, passkeys, recent devices
  PATCH  /me/security               {login_alerts}
  POST   /me/2fa/setup              → {secret, otpauth_uri}   (off until /enable confirms a code)
  POST   /me/2fa/enable             {code}
  POST   /me/2fa/disable            {password, code}
  POST   /me/passkeys/options       → WebAuthn creation options + ticket   ("Biometric unlock")
  POST   /me/passkeys               {ticket, credential, name?}
  DELETE /me/passkeys/{id}          (or /me/passkeys to remove all)
  POST   /passkey/options           → WebAuthn request options + ticket   (sign-in page)
  POST   /passkey/login             {ticket, credential, device_id?} → tokens

Passkeys use the device's own fingerprint / face / PIN (user verification required).
The private key never leaves the device; we keep the public key only. A passkey
sign-in skips the authenticator-app code: it is already two factors (the device +
the biometric/PIN).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_db, get_settings
from app.core import totp
from app.core.crypto import decrypt_str, encrypt_str
from app.core.dependencies import get_current_user
from app.core.security import create_ticket, decode_ticket, verify_password
from app.models import User, UserDevice, UserPasskey
from app.schemas.auth import TokenResponse
from app.services.user_signin import complete_sign_in, describe_agent
from app.utils.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth-security"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

MAX_PASSKEYS = 10


# ── bodies ──────────────────────────────────────────────────────────────────

class MfaBody(BaseModel):
    mfa_token: str
    code: str
    device_id: str | None = Field(default=None, max_length=100)


class CodeBody(BaseModel):
    code: str


class DisableBody(BaseModel):
    password: str
    code: str


class SecurityPatch(BaseModel):
    login_alerts: bool


class PasskeyRegisterBody(BaseModel):
    ticket: str
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=60)


class PasskeyLoginBody(BaseModel):
    ticket: str
    credential: dict[str, Any]
    device_id: str | None = Field(default=None, max_length=100)


# ── helpers ─────────────────────────────────────────────────────────────────

def _rp() -> tuple[str, str]:
    """(rp_id, expected origin) from PUBLIC_APP_URL — e.g. ("localhost", "http://localhost:5173")."""
    url = urlparse(get_settings().PUBLIC_APP_URL)
    return url.hostname or "localhost", f"{url.scheme}://{url.netloc}"


def _check_code(user: User, code: str) -> None:
    """Accept an authenticator code once (replay-safe). Caller commits."""
    if not user.totp_secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-factor authentication isn't set up")
    step = totp.verify(decrypt_str(user.totp_secret_enc), code, user.totp_last_step)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has already been used — try the next one")
    user.totp_last_step = step


async def _security(db: AsyncSession, user: User) -> dict[str, Any]:
    keys = (await db.exec(select(UserPasskey).where(UserPasskey.user_id == user.id)
                          .order_by(col(UserPasskey.created_at)))).all()
    devices = (await db.exec(select(UserDevice).where(UserDevice.user_id == user.id)
                             .order_by(col(UserDevice.last_seen_at).desc()).limit(10))).all()
    return {
        "two_factor_enabled": user.totp_enabled_at is not None,
        "login_alerts": user.login_alerts,
        "passkeys": [{"id": k.id, "name": k.name, "created_at": k.created_at, "last_used_at": k.last_used_at}
                     for k in keys],
        "devices": [{"device": describe_agent(d.user_agent), "ip": d.ip, "first_seen_at": d.first_seen_at,
                     "last_seen_at": d.last_seen_at} for d in devices],
    }


# ── two-factor sign-in ──────────────────────────────────────────────────────

@router.post("/login/2fa", response_model=TokenResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def login_2fa(request: Request, body: MfaBody, db: Db) -> TokenResponse:
    try:
        user_id = decode_ticket(body.mfa_token, "user_mfa")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired — enter your password again")
    user = await db.get(User, user_id)
    if user is None or user.totp_enabled_at is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired — enter your password again")
    _check_code(user, body.code)
    db.add(user)
    access, refresh = await complete_sign_in(db, user, request, body.device_id)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.get("/me/security")
async def get_security(user: CurrentUser, db: Db) -> dict[str, Any]:
    return await _security(db, user)


@router.patch("/me/security")
async def update_security(body: SecurityPatch, user: CurrentUser, db: Db) -> dict[str, Any]:
    user.login_alerts = body.login_alerts
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await _security(db, user)


@router.post("/me/2fa/setup")
async def setup_2fa(user: CurrentUser, db: Db) -> dict[str, str]:
    if user.totp_enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on")
    secret = totp.new_secret()
    user.totp_secret_enc, user.totp_last_step = encrypt_str(secret), None
    db.add(user)
    await db.commit()
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.email, issuer="FOID")}


@router.post("/me/2fa/enable")
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def enable_2fa(request: Request, body: CodeBody, user: CurrentUser, db: Db) -> dict[str, Any]:
    if user.totp_enabled_at is None:
        _check_code(user, body.code)
        user.totp_enabled_at = datetime.now(timezone.utc)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return await _security(db, user)


@router.post("/me/2fa/disable")
@limiter.limit("5/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def disable_2fa(request: Request, body: DisableBody, user: CurrentUser, db: Db) -> dict[str, Any]:
    if user.totp_enabled_at is not None:
        if not verify_password(body.password, user.hashed_password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is wrong")
        _check_code(user, body.code)
        user.totp_secret_enc = user.totp_enabled_at = user.totp_last_step = None
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return await _security(db, user)


# ── passkeys (Biometric unlock) ─────────────────────────────────────────────

@router.post("/me/passkeys/options")
async def passkey_register_options(user: CurrentUser, db: Db) -> dict[str, Any]:
    keys = (await db.exec(select(UserPasskey).where(UserPasskey.user_id == user.id))).all()
    if len(keys) >= MAX_PASSKEYS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can have up to {MAX_PASSKEYS} passkeys — remove one first")
    rp_id, _ = _rp()
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="FOID", user_id=user.id.encode(), user_name=user.email,
        user_display_name=f"{user.first_name} {user.last_name}",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(k.credential_id)) for k in keys],
    )
    ticket = create_ticket(f"{user.id}|{bytes_to_base64url(opts.challenge)}", "passkey_register")
    return {"ticket": ticket, "options": json.loads(options_to_json(opts))}


@router.post("/me/passkeys")
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def passkey_register(request: Request, body: PasskeyRegisterBody, user: CurrentUser, db: Db) -> dict[str, Any]:
    try:
        owner, challenge = decode_ticket(body.ticket, "passkey_register").split("|", 1)
    except (JWTError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Setup took too long — try again")
    if owner != user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Setup took too long — try again")
    rp_id, origin = _rp()
    try:
        v = verify_registration_response(credential=body.credential, expected_challenge=base64url_to_bytes(challenge),
                                         expected_rp_id=rp_id, expected_origin=origin, require_user_verification=True)
    except InvalidRegistrationResponse:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This device's passkey couldn't be verified")
    cred_id = bytes_to_base64url(v.credential_id)
    if (await db.exec(select(UserPasskey).where(UserPasskey.credential_id == cred_id))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This passkey is already set up")
    db.add(UserPasskey(user_id=user.id, credential_id=cred_id, public_key=v.credential_public_key,
                       sign_count=v.sign_count, name=body.name or describe_agent(request.headers.get("user-agent"))))
    await db.commit()
    return await _security(db, user)


@router.delete("/me/passkeys")
async def passkeys_remove_all(user: CurrentUser, db: Db) -> dict[str, Any]:
    for k in (await db.exec(select(UserPasskey).where(UserPasskey.user_id == user.id))).all():
        await db.delete(k)
    await db.commit()
    return await _security(db, user)


@router.delete("/me/passkeys/{passkey_id}")
async def passkey_remove(passkey_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    k = await db.get(UserPasskey, passkey_id)
    if k is None or k.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passkey not found")
    await db.delete(k)
    await db.commit()
    return await _security(db, user)


@router.post("/passkey/options")
@limiter.limit("20/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def passkey_login_options(request: Request) -> dict[str, Any]:
    """Discoverable sign-in: the device offers whichever FOID passkeys it holds (no email needed)."""
    rp_id, _ = _rp()
    opts = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    return {"ticket": create_ticket(bytes_to_base64url(opts.challenge), "passkey_login"),
            "options": json.loads(options_to_json(opts))}


@router.post("/passkey/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def passkey_login(request: Request, body: PasskeyLoginBody, db: Db) -> TokenResponse:
    bad = HTTPException(status.HTTP_401_UNAUTHORIZED, "That passkey isn't set up for a FOID account on this device")
    try:
        challenge = decode_ticket(body.ticket, "passkey_login")
    except JWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign-in took too long — try again")
    cred_id = body.credential.get("id")
    key = (await db.exec(select(UserPasskey).where(UserPasskey.credential_id == cred_id))).first() if isinstance(cred_id, str) else None
    if key is None:
        raise bad
    rp_id, origin = _rp()
    try:
        v = verify_authentication_response(
            credential=body.credential, expected_challenge=base64url_to_bytes(challenge), expected_rp_id=rp_id,
            expected_origin=origin, credential_public_key=key.public_key,
            credential_current_sign_count=key.sign_count, require_user_verification=True)
    except InvalidAuthenticationResponse:
        raise bad
    user = await db.get(User, key.user_id)
    if user is None:
        raise bad
    key.sign_count, key.last_used_at = v.new_sign_count, datetime.now(timezone.utc)
    db.add(key)
    access, refresh = await complete_sign_in(db, user, request, body.device_id)
    return TokenResponse(access_token=access, refresh_token=refresh)

