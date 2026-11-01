"""Connected banks router.

Endpoints:
  POST   /banks/exchange-token      — exchange Mono Connect code → store ConnectedBank
  GET    /banks/connected           — list all connected banks for the user
  POST   /banks/{id}/sync           — re-fetch account details from Mono
  DELETE /banks/{id}                — disconnect (delete) a bank record
  GET    /banks/{id}/transactions   — proxy Mono transaction list
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from httpx import ConnectTimeout, TimeoutException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db
from ..core.dependencies import get_current_user, require_verified_email
from ..models.connected_bank import ConnectedBank
from ..models.user import User
from ..schemas.bank import ConnectedBankOut, ExchangeTokenRequest, TransactionOut
from ..services import mono_service
from ..services.bank_logo_service import resolve_logo

router = APIRouter(prefix="/banks", tags=["banks"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_bank_or_404(bank_id: str, user: User, db: AsyncSession) -> ConnectedBank:
    result = await db.exec(
        select(ConnectedBank).where(
            ConnectedBank.id == bank_id,
            ConnectedBank.user_id == user.id,
        )
    )
    bank = result.first()
    if bank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank not found")
    return bank


@router.post("/exchange-token", response_model=ConnectedBankOut, status_code=status.HTTP_201_CREATED)
async def exchange_token(
    body: ExchangeTokenRequest,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> ConnectedBankOut:
    """Exchange a Mono Connect code for a permanent account ID and store it."""
    try:
        auth_raw: Any = await mono_service.exchange_code(body.code)
    except (ConnectTimeout, TimeoutException) as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Mono API timed out. Please try again.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        try:
            mono_detail = exc.response.json()
        except Exception:
            mono_detail = exc.response.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mono exchange failed ({exc.response.status_code}): {mono_detail}",
        ) from exc

    # v2 response: { "status": "successful", "data": { "id": "...", "account": {...} } }
    auth_data: Any = auth_raw.get("data") or auth_raw
    mono_account_id: str = auth_data.get("id", "")
    if not mono_account_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Mono returned no account ID")

    # Fetch full account details
    try:
        acct: Any = await mono_service.get_account(mono_account_id)
    except httpx.HTTPStatusError as exc:
        try:
            mono_detail = exc.response.json()
        except Exception:
            mono_detail = exc.response.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mono account fetch failed ({exc.response.status_code}): {mono_detail}",
        ) from exc

    # v2 response: { "status": "successful", "data": { "account": { "institution": {...}, ... } } }
    acct_data: Any = acct.get("data") or acct
    institution: Any = acct_data.get("account", {}).get("institution", {})
    name: str = institution.get("name", "Unknown Bank")
    account_type: str | None = acct_data.get("account", {}).get("type")
    masked_number: str | None = acct_data.get("account", {}).get("accountNumber")
    logo_url: str | None = await resolve_logo(
        institution_id=institution.get("id"),
        bank_code=institution.get("bank_code"),
        institution_name=name,
    )

    bank = ConnectedBank(
        user_id=current_user.id,
        mono_account_id=mono_account_id,
        name=name,
        account_type=account_type,
        masked_number=masked_number,
        logo_url=logo_url,
        status="verified",
        last_synced_at=_now(),
    )
    db.add(bank)
    await db.commit()
    await db.refresh(bank)
    return ConnectedBankOut.model_validate(bank)


@router.get("/connected", response_model=list[ConnectedBankOut])
async def list_connected_banks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectedBankOut]:
    """Return all connected banks for the authenticated user."""
    result = await db.exec(
        select(ConnectedBank).where(ConnectedBank.user_id == current_user.id)
    )
    return [ConnectedBankOut.model_validate(b) for b in result.all()]


@router.post("/{bank_id}/sync", response_model=ConnectedBankOut)
async def sync_bank(
    bank_id: str,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> ConnectedBankOut:
    """Re-fetch account details from Mono and update the stored record."""
    bank = await _get_bank_or_404(bank_id, current_user, db)

    try:
        acct: Any = await mono_service.get_account(bank.mono_account_id)
        acct_data: Any = acct.get("data") or acct
        institution: Any = acct_data.get("account", {}).get("institution", {})
        bank.name = institution.get("name", bank.name)
        bank.account_type = acct_data.get("account", {}).get("type", bank.account_type)
        resolved = await resolve_logo(
            institution_id=institution.get("id"),
            bank_code=institution.get("bank_code"),
            institution_name=bank.name,
        )
        if resolved:
            bank.logo_url = resolved
        bank.status = "verified"
        bank.last_synced_at = _now()
    except httpx.HTTPStatusError:
        bank.status = "error"
        bank.last_synced_at = _now()

    db.add(bank)
    await db.commit()
    await db.refresh(bank)
    return ConnectedBankOut.model_validate(bank)


@router.delete("/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_bank(
    bank_id: str,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a connected bank record."""
    bank = await _get_bank_or_404(bank_id, current_user, db)
    await db.delete(bank)
    await db.commit()


@router.get("/{bank_id}/transactions", response_model=list[TransactionOut])
async def get_bank_transactions(
    bank_id: str,
    start: str | None = Query(default=None, description="Start date YYYY-MM-DD"),
    end: str | None = Query(default=None, description="End date YYYY-MM-DD"),
    limit: int = Query(default=100, ge=1, le=500),
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionOut]:
    """Proxy Mono transaction list for a connected account."""
    bank = await _get_bank_or_404(bank_id, current_user, db)

    try:
        data: Any = await mono_service.get_transactions(
            bank.mono_account_id, start=start, end=end, limit=limit, page=page
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mono transactions fetch failed: {exc.response.status_code}",
        ) from exc

    raw_list: list[Any] = data.get("data", [])
    return [
        TransactionOut(
            id=tx.get("_id", ""),
            amount=tx.get("amount", 0),
            type=tx.get("type", ""),
            balance=tx.get("balance", 0),
            date=tx.get("date", ""),
            narration=tx.get("narration", ""),
            category=tx.get("category"),
        )
        for tx in raw_list
    ]
