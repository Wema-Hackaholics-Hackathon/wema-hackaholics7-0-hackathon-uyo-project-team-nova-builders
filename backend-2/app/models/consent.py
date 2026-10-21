# pyright: ignore[reportImportCycles]
"""Consent model — data-sharing permission granted by a user to a platform.

`status` values:
    pending   — awaiting user decision (Approve / Deny buttons shown)
    approved  — user approved; platform may access the agreed scope
    revoked   — access has been revoked (deny = revoke immediately)

ON DELETE CASCADE: deleting a User removes all their consent rows.
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


class Consent(SQLModel, table=True):
    __tablename__: ClassVar[str] = "consents"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # Platform requesting access, e.g. "Wema Bank", "Opay"
    platform: str
    # Human-readable scope, e.g. "Bank statement · 90 days"
    scope: str
    # pending | approved | revoked
    status: str = Field(default="pending")
    requested_at: datetime = Field(default_factory=_now)
    # Optional expiry — null means no expiry
    expires_at: datetime | None = Field(default=None)
    # Optional logo URL for the requesting platform
    logo_url: str | None = Field(default=None)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="consents",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
