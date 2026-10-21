"""Ledger schemas — request/response models for the AI Business Ledger API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class LedgerEntryOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    entry_date: date
    description: str
    category: str
    entry_type: str
    amount: Decimal
    source: str
    confidence: float
    raw_file_path: str | None
    created_at: datetime


class LedgerEntryUpdate(BaseModel):
    description: str | None = None
    category: str | None = None
    amount: Decimal | None = None


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []   # prior turns for multi-turn context


class ChatResponse(BaseModel):
    reply: str
    credits_remaining: int
