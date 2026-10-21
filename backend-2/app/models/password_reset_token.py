# pyright: ignore[reportImportCycles]
"""Password reset token model.

Two-phase forgot-password flow:
  Phase 1 — user requests reset:
      * A 6-digit OTP is generated and emailed.
      * SHA-256(otp) is stored in `code_hash`.
      * `reset_token_hash` is NULL at this point.

  Phase 2 — user submits OTP:
      * OTP is verified against `code_hash`.
      * A UUID reset token is generated and returned to the client.
      * SHA-256(reset_token) is stored in `reset_token_hash`.
      * The raw OTP is no longer needed.

  Phase 3 — user submits new password:
      * reset_token is verified against `reset_token_hash`.
      * Password is updated; `used` is set to True.

Only one active (used=False, not expired) row per user is allowed.
Older rows are soft-invalidated (used=True) when a new request is made.

ON DELETE CASCADE: deleting a User removes all their reset token rows.
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


class PasswordResetToken(SQLModel, table=True):
    __tablename__: ClassVar[str] = "password_reset_tokens"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # SHA-256 of the UUID reset token issued after OTP verification (null until phase 2)
    reset_token_hash: str | None = Field(default=None)
    # True once the password has been changed (phase 3 complete) or superseded
    used: bool = Field(default=False)
    expires_at: datetime
    created_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )
