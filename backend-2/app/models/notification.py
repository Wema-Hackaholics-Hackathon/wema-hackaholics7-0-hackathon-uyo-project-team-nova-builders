# pyright: ignore[reportImportCycles]
"""Notification model — immutable audit log of credential state changes.

Every credential state transition MUST produce one Notification row.
Matches the Notification interface in frontend/src/types/foid.ts.

ON DELETE CASCADE: deleting a User removes all their notifications.
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


class Notification(SQLModel, table=True):
    __tablename__: ClassVar[str] = "notifications"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # Human-readable title, e.g. "Credential placed Under Review"
    message: str
    # Transition description, e.g. "active → under_review"
    change: str
    # Reason shown to user
    reason: str
    # Suggested action for user
    action: str
    timestamp: datetime = Field(default_factory=_now)
    read: bool = Field(default=False)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="notifications",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
