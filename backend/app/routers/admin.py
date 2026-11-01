"""Admin router — /api/v1/admin/*

All endpoints require the requesting user to have is_admin=True.
Non-admins receive HTTP 403.

Endpoints
---------
GET  /admin/users                              List all users (id, name, email, flags)
GET  /admin/users/{user_id}                    Full user profile + credential
PATCH /admin/users/{user_id}/verifications     Flip nin_verified / phone_verified /
                                               bill_verified / bvn_validated on a user's
                                               credential claims
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db
from ..core.dependencies import get_current_user
from ..models.credential import Credential
from ..models.user import User
from ..schemas.auth import UserOut
from ..schemas.credential import CredentialOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Admin guard dependency
# ---------------------------------------------------------------------------

async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Raise HTTP 403 if the authenticated user is not an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class AdminUserSummary(BaseModel):
    """Lightweight user row for the admin user list."""
    id: str
    first_name: str
    last_name: str
    email: str
    is_admin: bool
    # Quick-glance verification flags pulled from credential claims
    bvn_validated: bool
    nin_verified: bool
    phone_verified: bool
    bill_verified: bool
    email_verified: bool


class AdminUserDetail(UserOut):
    """Full user profile plus their credential, for the admin detail view."""
    is_admin: bool
    credential: CredentialOut | None


class VerificationPatchRequest(BaseModel):
    """All fields are optional — only the ones supplied will be updated."""
    bvn_validated: bool | None = None
    nin_verified: bool | None = None
    phone_verified: bool | None = None
    bill_verified: bool | None = None
    email_verified: bool | None = None


# ---------------------------------------------------------------------------
# GET /admin/users  — list all users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[AdminUserSummary])
async def list_users(
    _admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminUserSummary]:
    """Return a summary row for every registered user."""
    users_result = await db.exec(select(User))
    users = users_result.all()

    rows: list[AdminUserSummary] = []
    for u in users:
        claims: dict = dict(u.credential.claims) if u.credential else {}
        rows.append(AdminUserSummary(
            id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            email=u.email,
            is_admin=u.is_admin,
            bvn_validated=bool(claims.get("bvn_validated", False)),
            nin_verified=bool(claims.get("nin_verified", False)),
            phone_verified=bool(claims.get("phone_verified", False)),
            bill_verified=bool(claims.get("bill_verified", False)),
            email_verified=bool(claims.get("email_verified", True)),
        ))
    return rows


# ---------------------------------------------------------------------------
# GET /admin/users/{user_id}  — full detail
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: str,
    _admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserDetail:
    """Return full profile + credential for a single user."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    cred_out = CredentialOut.model_validate(user.credential) if user.credential else None

    return AdminUserDetail(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        middle_name=user.middle_name,
        nin=user.nin,
        bvn=user.bvn,
        phone=user.phone,
        address=user.address,
        proof_of_address_url=user.proof_of_address_url,
        email=user.email,
        created_at=user.created_at,
        is_admin=user.is_admin,
        credential=cred_out,
    )


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}/verifications  — flip verification flags
# ---------------------------------------------------------------------------

@router.patch("/users/{user_id}/verifications", response_model=CredentialOut)
async def update_verifications(
    user_id: str,
    body: VerificationPatchRequest,
    _admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CredentialOut:
    """Flip any combination of bvn_validated / nin_verified / phone_verified /
    bill_verified on the user's credential claims.

    Only the fields explicitly included in the request body are changed.
    Returns the updated CredentialOut.
    """
    from datetime import datetime, timezone

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    cred_result = await db.exec(select(Credential).where(Credential.user_id == user_id))
    cred = cred_result.first()
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    # Build updated claims — only touch the keys that were supplied
    updated: dict = dict(cred.claims)
    if body.bvn_validated is not None:
        updated["bvn_validated"] = body.bvn_validated
    if body.nin_verified is not None:
        updated["nin_verified"] = body.nin_verified
    if body.phone_verified is not None:
        updated["phone_verified"] = body.phone_verified
    if body.bill_verified is not None:
        updated["bill_verified"] = body.bill_verified
    if body.email_verified is not None:
        updated["email_verified"] = body.email_verified

    cred.claims = updated  # type: ignore[assignment]
    cred.updated_at = datetime.now(timezone.utc)
    db.add(cred)
    await db.commit()
    await db.refresh(cred)

    return CredentialOut.model_validate(cred)
