# pyright: ignore[reportImportCycles]
"""Connected bank account model — linked via Mono Open Banking.

Flow:
    1. Frontend opens Mono Connect widget → user authorises → widget returns `code`
    2. Frontend POSTs `code` to POST /api/v1/banks/exchange-token
    3. Backend calls Mono /account/auth to get `mono_account_id`
    4. Backend stores this row; subsequent syncs use `mono_account_id`

`status` values:
    verified  — connection healthy, last sync succeeded
    error     — last sync failed (e.g. re-auth required)
    pending   — token exchanged but first sync not yet completed

ON DELETE CASCADE: deleting a User removes all their connected bank rows.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Optional

from sqlalchemy import ForeignKey, String
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User  # pyright: ignore[reportImportCycles]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectedBank(SQLModel, table=True):
    __tablename__: ClassVar[str] = "connected_banks"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # Mono's permanent account identifier — used for all subsequent API calls
    mono_account_id: str = Field(unique=True, index=True)
    name: str
    account_type: str | None = Field(default=None)
    masked_number: str | None = Field(default=None)
    # verified | error | pending
    status: str = Field(default="pending")
    logo_url: str | None = Field(default=None)
    last_synced_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="connected_banks",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
