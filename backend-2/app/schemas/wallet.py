"""Wallet schemas — request/response models for the credit wallet API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class WalletOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    balance: int
    auto_topup_threshold: int | None
    updated_at: datetime


class WalletTransactionOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    transaction_type: str
    credits_delta: int
    feature: str
    paystack_reference: str | None
    status: str | None
    created_at: datetime


class PurchaseInitRequest(BaseModel):
    # Credit package identifier — maps to an amount in kobo
    package: str   # "starter" | "growth" | "topup"


class PurchaseInitResponse(BaseModel):
    authorization_url: str
    reference: str
    credits: int
    amount_ngn: int


class AutoTopupRequest(BaseModel):
    threshold: int | None  # null = disable auto top-up
