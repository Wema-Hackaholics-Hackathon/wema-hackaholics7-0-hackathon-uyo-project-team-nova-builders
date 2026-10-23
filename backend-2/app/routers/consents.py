"""Consents router.

Endpoints:
  GET    /consents              — list user's consents (optional ?status= filter)
  POST   /consents              — create a new consent request
  PATCH  /consents/{id}         — approve or revoke a consent

The seed function is called from auth signup to insert demo consents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db
from ..core.dependencies import get_current_user, require_verified_email
from ..models.consent import Consent
from ..models.user import User
from ..schemas.consent import ConsentCreate, ConsentOut, ConsentUpdate

router = APIRouter(prefix="/consents", tags=["consents"])


@router.get("", response_model=list[ConsentOut])
async def list_consents(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConsentOut]:
    """Return consents for the current user, optionally filtered by status."""
    stmt = select(Consent).where(Consent.user_id == current_user.id)
    if status_filter in ("pending", "approved", "revoked"):
        stmt = stmt.where(Consent.status == status_filter)
    result = await db.exec(stmt)
    return [ConsentOut.model_validate(c) for c in result.all()]


@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
async def create_consent(
    body: ConsentCreate,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut:
    """Create a new consent request (platform sends this on behalf of user)."""
    consent = Consent(
        user_id=current_user.id,
        platform=body.platform,
        scope=body.scope,
        status="pending",
        expires_at=body.expires_at,
        logo_url=body.logo_url,
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)
    return ConsentOut.model_validate(consent)


@router.patch("/{consent_id}", response_model=ConsentOut)
async def update_consent(
    consent_id: str,
    body: ConsentUpdate,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut:
    """Approve or revoke a consent. Deny = revoke immediately."""
    result = await db.exec(
        select(Consent).where(
            Consent.id == consent_id,
            Consent.user_id == current_user.id,
        )
    )
    consent = result.first()
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")

    consent.status = body.status
    db.add(consent)
    await db.commit()
    await db.refresh(consent)
    return ConsentOut.model_validate(consent)
