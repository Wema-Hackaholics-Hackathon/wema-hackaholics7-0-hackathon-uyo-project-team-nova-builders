"""Credentials router — GET /credentials/me, POST /credentials/trigger, FOID code.

FOID code ("View my FOID code" on the overview): POST /credentials/me/code returns a
short-lived, encrypted token the user shows as a QR code. Anyone who scans it opens
GET /credentials/code/{token} (no login) and sees only: first name + last initial,
the credential state and yes/no claims — never NIN, BVN, DOB, email or phone. The
token expires after CODE_TTL_SECONDS and the state is read live on every scan.
"""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db, get_settings
from ..core.api_errors import ApiError
from ..core.crypto import decrypt_str, encrypt_str
from ..core.dependencies import get_current_user, require_verified_email
from ..models.credential import Credential
from ..models.user import User
from ..schemas.credential import CredentialOut, TriggerRequest, TriggerResponse
from ..schemas.notification import NotificationOut
from ..services.credential_service import apply_trigger
from ..utils.limiter import limiter

router = APIRouter(prefix="/credentials", tags=["credentials"])


async def _get_credential_or_404(user: User, db: AsyncSession) -> Credential:
    result = await db.exec(select(Credential).where(Credential.user_id == user.id))
    credential = result.first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    return credential


@router.get("/me", response_model=CredentialOut)
async def get_my_credential(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialOut:
    """Return the authenticated user's FOID credential."""
    credential = await _get_credential_or_404(current_user, db)
    return CredentialOut.model_validate(credential)


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_event(
    body: TriggerRequest,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> TriggerResponse:
    """Apply a trigger event to the credential.

    Returns HTTP 409 if the current state does not satisfy the event's
    requiredState guard.
    """
    credential = await _get_credential_or_404(current_user, db)

    updated_cred, notif = await apply_trigger(
        credential=credential,
        event=body.event,  # type: ignore[arg-type]
        db=db,
    )

    await db.commit()
    await db.refresh(updated_cred)
    await db.refresh(notif)

    return TriggerResponse(
        credential=CredentialOut.model_validate(updated_cred),
        notification=NotificationOut.model_validate(notif),
    )


# ── FOID code ────────────────────────────────────────────────────────────────

CODE_TTL_SECONDS = 600


def _foid_code(user_id: str) -> str:
    hexed = user_id.replace("-", "").upper()
    return f"FOID-{hexed[:4]}-{hexed[4:8]}"


def _over_18(dob: str | None) -> bool | None:
    try:
        born = date.fromisoformat(dob or "")
    except ValueError:
        return None
    today = date.today()
    return (today.year - born.year - ((today.month, today.day) < (born.month, born.day))) >= 18


@router.post("/me/code")
async def create_foid_code(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """A new scannable code, valid for 10 minutes. Codes are not stored."""
    token = encrypt_str(json.dumps({"u": current_user.id, "n": secrets.token_hex(4)}))
    expires = datetime.now(timezone.utc) + timedelta(seconds=CODE_TTL_SECONDS)
    return {
        "token": token,
        "url": f"{get_settings().PUBLIC_APP_URL.rstrip('/')}/c/{token}",
        "code": _foid_code(current_user.id),
        "expires_at": expires.isoformat(),
        "ttl_seconds": CODE_TTL_SECONDS,
    }


@router.get("/code/{token}")
@limiter.limit("30/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def check_foid_code(request: Request, token: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Public: what the person showing this code has verified. Deliberately minimal."""
    try:
        user_id = json.loads(decrypt_str(token, ttl=CODE_TTL_SECONDS))["u"]
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise ApiError(404, "code_invalid", "This FOID code has expired or isn't valid. Ask for a fresh one.")
    user = await db.get(User, user_id)
    credential = (await db.exec(select(Credential).where(Credential.user_id == user_id))).first()
    if user is None or credential is None:
        raise ApiError(404, "code_invalid", "This FOID code has expired or isn't valid. Ask for a fresh one.")
    nin_ok = user.nin_verified_at is not None
    return {
        "holder": f"{user.first_name} {user.last_name[:1]}.".strip(),
        "code": _foid_code(user.id),
        "state": credential.state,
        "checks": {
            "liveness": user.liveness_verified_at is not None,
            "nin": nin_ok,
            "bvn": user.bvn_verified_at is not None,
            "email": bool((credential.claims or {}).get("email_verified", False)),
            # Only from a NIN-verified date of birth; never the date itself.
            "age_over_18": _over_18(user.date_of_birth) if nin_ok else None,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
