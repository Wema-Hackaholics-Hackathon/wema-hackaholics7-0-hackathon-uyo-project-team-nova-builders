"""Wallet service — credit deduction and monthly free refresh.

Two-bucket spending rule:
    1. free_credits are drained first
    2. paid_credits are drained only once free_credits are exhausted

Monthly free refresh (lazy):
    - Called on every wallet read and before every deduction
    - If the current calendar month differs from last_free_refresh,
      free_credits is reset to FREE_MONTHLY_CREDITS
    - Paid credits are never touched by the refresh

deduct_credits():
    - Applies the monthly refresh before checking balance
    - Raises HTTP 402 if total balance (free + paid) < required
    - Records the credit_type ("free", "paid", "mixed") on the transaction
    - Caller must commit
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_settings
from ..models.wallet import Wallet, WalletTransaction


def _current_month() -> str:
    """Return the current calendar month as 'YYYY-MM'."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def apply_monthly_refresh(wallet: Wallet) -> bool:
    """Reset free_credits if a new calendar month has started.

    Mutates wallet in-place. Returns True if a refresh was applied
    (caller should add wallet to the session and commit).
    """
    month = _current_month()
    if wallet.last_free_refresh == month:
        return False  # already refreshed this month

    wallet.free_credits = get_settings().FREE_MONTHLY_CREDITS
    wallet.last_free_refresh = month
    wallet.updated_at = datetime.now(timezone.utc)
    return True


class InsufficientCreditsError(Exception):
    pass


async def deduct_credits(
    *,
    user_id: str,
    amount: int,
    feature: str,
    db: AsyncSession,
) -> Wallet:
    """Deduct `amount` credits from the user's wallet (free first, then paid).

    - Applies the monthly free refresh before checking the balance.
    - Raises HTTP 402 if free_credits + paid_credits < amount.
    - Records credit_type = "free" | "paid" | "mixed" on the transaction.
    - Caller must commit after calling this function.

    Returns the updated Wallet instance (not yet committed).
    """
    result = await db.exec(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.first()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    # Apply monthly refresh (may change free_credits)
    apply_monthly_refresh(wallet)

    total = wallet.free_credits + wallet.paid_credits
    if total < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient credits: need {amount}, "
                f"have {wallet.free_credits} free + {wallet.paid_credits} paid = {total}"
            ),
        )

    # Determine which buckets are consumed and record credit_type
    if wallet.free_credits >= amount:
        # All from free bucket
        wallet.free_credits -= amount
        credit_type = "free"
    elif wallet.free_credits == 0:
        # All from paid bucket
        wallet.paid_credits -= amount
        credit_type = "paid"
    else:
        # Mixed: drain free first, remainder from paid
        remainder = amount - wallet.free_credits
        wallet.free_credits = 0
        wallet.paid_credits -= remainder
        credit_type = "mixed"

    wallet.updated_at = datetime.now(timezone.utc)

    tx = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        transaction_type="usage",
        credits_delta=-amount,
        feature=feature,
        credit_type=credit_type,
        status=None,
    )
    db.add(wallet)
    db.add(tx)
    return wallet
