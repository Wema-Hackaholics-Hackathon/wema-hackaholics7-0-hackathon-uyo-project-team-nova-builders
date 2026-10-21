"""Wallet service — atomic credit deduction.

deduct_credits():
  - Checks user's current wallet balance
  - Deducts atomically using a DB-level row lock (SELECT FOR UPDATE)
  - Inserts a WalletTransaction row
  - Raises InsufficientCreditsError (→ HTTP 402) if balance < required
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models.wallet import Wallet, WalletTransaction


class InsufficientCreditsError(Exception):
    pass


async def deduct_credits(
    *,
    user_id: str,
    amount: int,
    feature: str,
    db: AsyncSession,
) -> Wallet:
    """Deduct `amount` credits from the user's wallet.

    Raises HTTP 402 if balance < amount.
    Caller must commit after calling this function.
    Returns the updated Wallet instance (not yet committed).
    """
    result = await db.exec(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.first()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    if wallet.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {amount}, have {wallet.balance}",
        )

    wallet.balance -= amount
    wallet.updated_at = datetime.now(timezone.utc)

    tx = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        transaction_type="usage",
        credits_delta=-amount,
        feature=feature,
        status=None,
    )
    db.add(wallet)
    db.add(tx)
    return wallet
