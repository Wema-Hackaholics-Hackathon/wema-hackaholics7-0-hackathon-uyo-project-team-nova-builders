# pyright: ignore[reportImportCycles]
"""Ledger entry model — AI-categorised income/expense transaction.

Entries are created either by:
  - Uploading a receipt/invoice (POST /api/v1/ledger/upload) — costs 4 credits
  - Manual creation (future)

`entry_type`: "income" | "expense"

`source`: "receipt" | "invoice" | "bank" | "manual"

`confidence`: 0.0–1.0 — how confident Groq was in the categorisation.

ON DELETE CASCADE: deleting a User removes all their ledger entries.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Optional

from sqlalchemy import ForeignKey, Numeric, String
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User  # pyright: ignore[reportImportCycles]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LedgerEntry(SQLModel, table=True):
    __tablename__: ClassVar[str] = "ledger_entries"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    # Date of the transaction (not necessarily today)
    entry_date: date
    description: str
    # e.g. "Payroll", "Logistics", "Software", "Marketing", "Sales", "Other"
    category: str
    # income | expense
    entry_type: str
    # Store as NUMERIC(15, 2) for precision — never use float for money
    amount: Decimal = Field(
        sa_column=Column(Numeric(precision=15, scale=2), nullable=False)
    )
    # receipt | invoice | bank | manual
    source: str = Field(default="manual")
    # 0.0–1.0 AI confidence score
    confidence: float = Field(default=1.0)
    # Path to the uploaded file (local or S3 key) — null for manual entries
    raw_file_path: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="ledger_entries",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
