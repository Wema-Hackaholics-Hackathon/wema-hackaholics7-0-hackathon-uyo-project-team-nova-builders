# pyright: ignore[reportImportCycles]
"""Wallet and wallet transaction models.

Wallet       — one per user; holds two separate credit buckets:
    free_credits   — granted FREE_MONTHLY_CREDITS every calendar month (lazy refresh)
    paid_credits   — purchased credits, never expire, carry forward forever

Spending rule: free_credits are drained first, paid_credits after.

The read-only property `balance` = free_credits + paid_credits.

WalletTransaction — append-only ledger of every credit movement:
    - Negative delta: AI feature usage (receipt scan, chat, etc.)
    - Positive delta: credit purchase via payment provider

`transaction_type` values:
    usage     — credits deducted for an AI feature
    purchase  — credits added after a verified payment

`credit_type` (usage rows only):
    free      — deducted entirely from free_credits
    paid      — deducted entirely from paid_credits
    mixed     — deducted from both buckets (free ran out mid-usage)

`status` (purchase rows only):
    pending   — payment initiated but webhook not yet received
    paid      — charge verified; credits have been added
    failed    — payment failed or webhook verification rejected

`last_free_refresh` — the calendar month (YYYY-MM) of the last free credit grant.
    Compared on every wallet read; if it differs from the current month,
    free_credits is reset to FREE_MONTHLY_CREDITS before the response is returned.

Cascade chain:
    users  --CASCADE-->  wallets  --CASCADE-->  wallet_transactions
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Optional

from sqlalchemy import ForeignKey, String
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Wallet(SQLModel, table=True):
    __tablename__: ClassVar[str] = "wallets"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    # One wallet per user — enforced via unique constraint
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            index=True,
            nullable=False,
        )
    )

    # ── Two credit buckets ───────────────────────────────────────────────────
    # Free credits — refreshed to FREE_MONTHLY_CREDITS each calendar month
    free_credits: int = Field(default=0)
    # Paid credits — accumulate indefinitely, never expire
    paid_credits: int = Field(default=0)

    # Last month free credits were granted, stored as "YYYY-MM" string.
    # Null = never refreshed (new wallet, refresh will fire on first read).
    last_free_refresh: str | None = Field(default=None)

    # Auto top-up: fires a new purchase when total balance drops below threshold
    auto_topup_threshold: int | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_now)

    @property
    def balance(self) -> int:
        """Total spendable credits = free + paid."""
        return self.free_credits + self.paid_credits

    # ── Relationships ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="wallet",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    transactions: list["WalletTransaction"] = Relationship(
        back_populates="wallet",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )


class WalletTransaction(SQLModel, table=True):
    __tablename__: ClassVar[str] = "wallet_transactions"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    wallet_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("wallets.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    # usage | purchase
    transaction_type: str
    # Negative for usage, positive for purchases
    credits_delta: int
    # Human-readable label e.g. "Receipt scan — Uber invoice", "Custom purchase — 300 credits"
    feature: str
    # Payment provider reference — only set for purchase rows
    paystack_reference: str | None = Field(default=None)
    # pending | paid | failed — only relevant for purchase rows
    status: str | None = Field(default=None)
    # free | paid | mixed — which bucket(s) were consumed (usage rows only)
    credit_type: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ─────────────────────────────────────────────────────────
    wallet: Optional["Wallet"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
