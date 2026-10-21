# pyright: ignore[reportImportCycles]
"""Wallet and wallet transaction models.

Wallet       — one per user; holds the current AI credit balance.
WalletTransaction — append-only ledger of every credit movement:
    - Negative delta: AI feature usage (receipt scan, chat, etc.)
    - Positive delta: credit purchase via Paystack

`transaction_type` values:
    usage     — credits deducted for an AI feature
    purchase  — credits added after a verified Paystack payment

`status` (purchase rows only):
    pending   — Paystack payment initiated but webhook not yet received
    paid      — charge.success webhook verified; credits have been added
    failed    — payment failed or webhook verification rejected

Cascade chain:
    users  --CASCADE-->  wallets  --CASCADE-->  wallet_transactions
Deleting a User removes their Wallet, which in turn removes all their
WalletTransaction rows.
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
    balance: int = Field(default=0)      # integer credits (never fractional)
    # Auto top-up fires a new purchase when balance drops below this threshold
    # null = auto top-up disabled
    auto_topup_threshold: int | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_now)

    # ── Relationships ───────────────────────────────────────────────────────
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
    # Human-readable label, e.g. "Receipt scan — Uber invoice", "Growth pack"
    feature: str
    # Paystack payment reference — only set for purchase rows
    paystack_reference: str | None = Field(default=None)
    # pending | paid | failed — only relevant for purchase rows
    status: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    wallet: Optional["Wallet"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
