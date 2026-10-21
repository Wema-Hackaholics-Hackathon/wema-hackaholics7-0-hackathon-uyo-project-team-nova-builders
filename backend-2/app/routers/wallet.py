"""AI Credit Wallet router.

Endpoints:
  GET    /wallet                   — current balance + transaction history
  POST   /wallet/initiate-purchase — create Paystack payment URL
  POST   /wallet/paystack-webhook  — receive Paystack charge.success (public, HMAC verified)
  POST   /wallet/auto-topup        — set/update auto top-up threshold
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db, get_settings
from ..core.dependencies import get_current_user
from ..models.user import User
from ..models.wallet import Wallet, WalletTransaction
from ..schemas.wallet import (
    AutoTopupRequest,
    PurchaseInitRequest,
    PurchaseInitResponse,
    WalletOut,
    WalletTransactionOut,
)
from ..services import paystack_service

router = APIRouter(prefix="/wallet", tags=["wallet"])

# Credit packages — mirrors frontend's AICreditWalletPage.tsx demo data
_PACKAGES: dict[str, dict[str, int]] = {
    "starter": {"credits": 5000,  "amount_ngn": 25000},
    "growth":  {"credits": 10000, "amount_ngn": 45000},
    "topup":   {"credits": 2500,  "amount_ngn": 12500},
}


async def _get_wallet_or_404(user_id: str, db: AsyncSession) -> Wallet:
    result = await db.exec(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.first()
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return wallet


class WalletWithHistory(WalletOut):
    transactions: list[WalletTransactionOut]


@router.get("", response_model=WalletWithHistory)
async def get_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletWithHistory:
    """Return wallet balance and full transaction history."""
    wallet = await _get_wallet_or_404(current_user.id, db)

    tx_result = await db.exec(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet.id)
        .order_by(col(WalletTransaction.created_at).desc())
    )
    transactions = [WalletTransactionOut.model_validate(t) for t in tx_result.all()]

    return WalletWithHistory(
        id=wallet.id,
        balance=wallet.balance,
        auto_topup_threshold=wallet.auto_topup_threshold,
        updated_at=wallet.updated_at,
        transactions=transactions,
    )


@router.post("/initiate-purchase", response_model=PurchaseInitResponse)
async def initiate_purchase(
    body: PurchaseInitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchaseInitResponse:
    """Initiate a Paystack payment for a credit package."""
    pkg = _PACKAGES.get(body.package)
    if pkg is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown package '{body.package}'. Choose: starter, growth, topup",
        )

    wallet = await _get_wallet_or_404(current_user.id, db)
    reference = str(uuid.uuid4())
    amount_kobo = pkg["amount_ngn"] * 100  # Paystack amounts are in kobo

    # Create a pending WalletTransaction row so the webhook can find it
    pending_tx = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        transaction_type="purchase",
        credits_delta=pkg["credits"],
        feature=f"{body.package.title()} pack — {pkg['credits']:,} credits",
        paystack_reference=reference,
        status="pending",
    )
    db.add(pending_tx)
    await db.commit()

    settings = get_settings()
    # Use the first allowed origin as the frontend base URL
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
                "credits": pkg["credits"],
                "package": body.package,
            },
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Paystack initialisation failed: {exc.response.status_code}",
        ) from exc

    authorization_url: str = result.get("data", {}).get("authorization_url", "")
    return PurchaseInitResponse(
        authorization_url=authorization_url,
        reference=reference,
        credits=pkg["credits"],
        amount_ngn=pkg["amount_ngn"],
    )


@router.post("/paystack-webhook", status_code=status.HTTP_200_OK)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Paystack charge.success webhook (public endpoint, HMAC verified)."""
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

    # Mark paid and credit the wallet
    pending_tx.status = "paid"
    db.add(pending_tx)

    wallet_result = await db.exec(
        select(Wallet).where(Wallet.id == pending_tx.wallet_id)
    )
    wallet = wallet_result.first()
    if wallet is not None:
        wallet.balance += pending_tx.credits_delta
        wallet.updated_at = datetime.now(timezone.utc)
        db.add(wallet)

    await db.commit()
    return {"status": "ok"}


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
