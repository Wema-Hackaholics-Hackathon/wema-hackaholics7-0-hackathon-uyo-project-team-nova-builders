"""LivenessSession model — tracks an active liveness challenge flow.

A session is created via POST /auth/me/liveness/start and expires after
LIVENESS_SESSION_TTL_MINUTES (default 10). The frontend must complete all
challenges within that window.

Columns:
    id            — UUID primary key
    user_id       — FK → users (CASCADE delete)
    challenges    — JSON list of challenge names issued (e.g. ["look_left", "open_mouth", "look_right"])
    completed     — JSON list of challenges the user has already passed (grows per verify call)
    expires_at    — hard expiry; backend rejects verify/complete after this
    created_at    — audit timestamp
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import ClassVar

from sqlalchemy import ForeignKey, JSON, String
from sqlmodel import Column, Field, SQLModel

# No Relationship needed — liveness router loads the user via get_current_user,
# not via this model.  Removing it avoids the SQLAlchemy generic-class error
# that occurs when Optional["User"] is used without a proper Mapped[] annotation.


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LivenessSession(SQLModel, table=True):
    __tablename__: ClassVar[str] = "liveness_sessions"  # pyright: ignore[reportIncompatibleVariableOverride]

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
    # JSON list — challenges issued in order, e.g. ["look_left", "open_mouth", "look_right"]
    challenges: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    # JSON list — grows as each challenge is verified successfully
    completed: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    expires_at: datetime
    created_at: datetime = Field(default_factory=_now)
