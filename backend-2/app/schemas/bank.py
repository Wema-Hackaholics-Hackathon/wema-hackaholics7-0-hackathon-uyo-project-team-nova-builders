"""Bank schemas — request/response models for the connected banks API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ExchangeTokenRequest(BaseModel):
    code: str


class ConnectedBankOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    mono_account_id: str
    name: str
    account_type: str | None
    masked_number: str | None
    status: str
    logo_url: str | None
    last_synced_at: datetime | None
    created_at: datetime


class TransactionOut(BaseModel):
    """Single Mono transaction — shape mirrors Mono's response object."""

    id: str
    amount: int           # in kobo
    type: str             # debit | credit
    balance: int          # running balance in kobo
    date: str             # ISO string from Mono
    narration: str
    category: str | None = None
