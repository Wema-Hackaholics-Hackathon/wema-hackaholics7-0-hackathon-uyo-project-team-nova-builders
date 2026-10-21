"""Wallet schemas — request/response models for the credit wallet API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class WalletOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    free_credits: int       # resets monthly
    paid_credits: int       # never expire
    balance: int            # free_credits + paid_credits (read-only)
    auto_topup_threshold: int | None
    updated_at: datetime


class WalletTransactionOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    transaction_type: str   # usage | purchase
    credits_delta: int
    feature: str
    paystack_reference: str | None
    status: str | None
    credit_type: str | None  # free | paid | mixed (usage rows only)
    created_at: datetime


class PurchaseInitResponse(BaseModel):
    authorization_url: str
    reference: str
    credits: int
    amount_ngn: int


class AutoTopupRequest(BaseModel):
    threshold: int | None  # null = disable auto top-up
