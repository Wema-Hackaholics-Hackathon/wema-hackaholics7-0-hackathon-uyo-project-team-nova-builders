# pyright: ignore[reportImportCycles]
"""Refresh token model — one row per issued refresh token.

Tokens are stored as a SHA-256 hash so the raw secret never persists.
Revoked tokens stay in the table for audit purposes.

ON DELETE CASCADE: deleting a User immediately removes all their refresh tokens.
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


class RefreshToken(SQLModel, table=True):
    __tablename__: ClassVar[str] = "refresh_tokens"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # SHA-256 hex digest of the raw token — never store the raw value
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="refresh_tokens",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
