# pyright: ignore[reportImportCycles]
"""Email verification token model.

A 6-digit OTP is generated at signup (and on resend request) and stored here.
Once the user submits the correct OTP via POST /auth/verify-email, the row is
marked used=True and the email_verified claim on their Credential is set True.

Only one active (used=False, not expired) row per user is kept.
Older rows are invalidated (used=True) whenever a new OTP is issued.

ON DELETE CASCADE: deleting a User removes all their verification token rows.
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


class EmailVerificationToken(SQLModel, table=True):
    __tablename__: ClassVar[str] = "email_verification_tokens"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # SHA-256 of the 6-digit OTP sent to the user's email
    code_hash: str
    used: bool = Field(default=False)
    expires_at: datetime
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )
