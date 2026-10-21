"""AI Credit Wallet router.

Endpoints:
  GET    /wallet                   — current balance (free + paid) + transaction history
  POST   /wallet/initiate-purchase — create Bachs checkout session for a custom NGN amount
  POST   /wallet/bachs-webhook     — receive collection.succeeded webhook (public, HMAC-SHA256 verified)
  POST   /wallet/auto-topup        — set/update auto top-up threshold

Credit pricing:
  ₦CREDIT_PRICE_NGN per credit (default ₦5)
  Minimum purchase: MIN_PURCHASE_NGN (default ₦500 → 100 credits)
  No fixed packages — user chooses any amount ≥ minimum.

Two credit buckets:
  free_credits   — reset to FREE_MONTHLY_CREDITS each calendar month (lazily on read)
  paid_credits   — accumulate forever, never expire

Spending order: free first, then paid.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db, get_settings
from ..core.dependencies import get_current_user
from ..models.user import User
from ..models.wallet import Wallet, WalletTransaction
from ..schemas.wallet import (
    AutoTopupRequest,
    PurchaseInitResponse,
    WalletOut,
    WalletTransactionOut,
)
from ..services import bachs_service
from ..services.wallet_service import apply_monthly_refresh

router = APIRouter(prefix="/wallet", tags=["wallet"])


# ---------------------------------------------------------------------------
# Local schemas (custom amount replaces the old package-based request)
# ---------------------------------------------------------------------------

class PurchaseInitRequest(BaseModel):
    amount_ngn: int     # any integer ≥ MIN_PURCHASE_NGN

    @field_validator("amount_ngn")
    @classmethod
    def must_meet_minimum(cls, v: int) -> int:
        minimum = get_settings().MIN_PURCHASE_NGN
        if v < minimum:
            raise ValueError(f"Minimum purchase is ₦{minimum:,}")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_wallet_or_404(user_id: str, db: AsyncSession) -> Wallet:
    result = await db.exec(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.first()
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return wallet


async def _read_wallet_with_refresh(user_id: str, db: AsyncSession) -> Wallet:
    """Load wallet and apply monthly free-credit refresh if needed."""
    wallet = await _get_wallet_or_404(user_id, db)
    refreshed = apply_monthly_refresh(wallet)
    if refreshed:
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
    return wallet


class WalletWithHistory(WalletOut):
    transactions: list[WalletTransactionOut]


# ---------------------------------------------------------------------------
# GET /wallet
# ---------------------------------------------------------------------------

@router.get("", response_model=WalletWithHistory)
async def get_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletWithHistory:
    """Return wallet balance breakdown (free + paid) and full transaction history.

    Applies the monthly free-credit refresh lazily before responding.
    """
    wallet = await _read_wallet_with_refresh(current_user.id, db)

    tx_result = await db.exec(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet.id)
        .order_by(col(WalletTransaction.created_at).desc())
    )
    transactions = [WalletTransactionOut.model_validate(t) for t in tx_result.all()]

    return WalletWithHistory(
        id=wallet.id,
        free_credits=wallet.free_credits,
        paid_credits=wallet.paid_credits,
        balance=wallet.balance,
        auto_topup_threshold=wallet.auto_topup_threshold,
        updated_at=wallet.updated_at,
        transactions=transactions,
    )


# ---------------------------------------------------------------------------
# POST /wallet/initiate-purchase
# ---------------------------------------------------------------------------

@router.post("/initiate-purchase", response_model=PurchaseInitResponse)
async def initiate_purchase(
    body: PurchaseInitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchaseInitResponse:
    """Initiate a payment for a custom NGN amount.

    Credits are calculated as: floor(amount_ngn / CREDIT_PRICE_NGN).
    Minimum purchase: MIN_PURCHASE_NGN.
    """
    settings = get_settings()
    credits = math.floor(body.amount_ngn / settings.CREDIT_PRICE_NGN)
    amount_kobo = body.amount_ngn * 100  # Paystack amounts are in kobo

    wallet = await _get_wallet_or_404(current_user.id, db)
    reference = str(uuid.uuid4())

    # Create a pending WalletTransaction so the webhook can find it
    pending_tx = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        transaction_type="purchase",
        credits_delta=credits,
        feature=f"Custom purchase — {credits:,} credits (₦{body.amount_ngn:,})",
        paystack_reference=reference,
        status="pending",
    )
    db.add(pending_tx)
    await db.commit()

    frontend_base = settings.ALLOWED_ORIGINS.split(",")[0].strip()
    callback_url = f"{frontend_base}/dashboard/wallet"

    try:
        result: Any = await paystack_service.initialize_transaction(
            email=current_user.email,
            amount_kobo=amount_kobo,
            reference=reference,
            callback_url=callback_url,
            metadata={
                "user_id": current_user.id,
                "credits": credits,
                "amount_ngn": body.amount_ngn,
            },
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment initialisation failed: {exc.response.status_code}",
        ) from exc

    authorization_url: str = result.get("data", {}).get("authorization_url", "")
    return PurchaseInitResponse(
        authorization_url=authorization_url,
        reference=reference,
        credits=credits,
        amount_ngn=body.amount_ngn,
    )


# ---------------------------------------------------------------------------
# POST /wallet/paystack-webhook  (public — no auth, HMAC verified)
# ---------------------------------------------------------------------------

@router.post("/paystack-webhook", status_code=status.HTTP_200_OK)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle charge.success webhook — credits are added to paid_credits only."""
    payload = await request.body()

    if not paystack_service.verify_webhook_signature(payload, x_paystack_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    import json as _json
    event: Any = _json.loads(payload)
    if event.get("event") != "charge.success":
        return {"status": "ignored"}

    reference: str = event.get("data", {}).get("reference", "")
    if not reference:
        return {"status": "no_reference"}

    # Find the pending WalletTransaction
    tx_result = await db.exec(
        select(WalletTransaction).where(
            WalletTransaction.paystack_reference == reference,
            WalletTransaction.status == "pending",
        )
    )
    pending_tx = tx_result.first()
    if pending_tx is None:
        return {"status": "not_found"}

    # Mark paid and top up the PAID bucket only
    pending_tx.status = "paid"
    db.add(pending_tx)

    wallet_result = await db.exec(
        select(Wallet).where(Wallet.id == pending_tx.wallet_id)
    )
    wallet = wallet_result.first()
    if wallet is not None:
        wallet.paid_credits += pending_tx.credits_delta
        wallet.updated_at = datetime.now(timezone.utc)
        db.add(wallet)

    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /wallet/auto-topup
# ---------------------------------------------------------------------------

@router.post("/auto-topup", response_model=WalletOut)
async def set_auto_topup(
    body: AutoTopupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    """Set or clear the auto top-up threshold (null = disabled)."""
    wallet = await _get_wallet_or_404(current_user.id, db)
    wallet.auto_topup_threshold = body.threshold
    wallet.updated_at = datetime.now(timezone.utc)
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)
    return WalletOut.model_validate(wallet)
