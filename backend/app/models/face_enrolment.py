"""Face enrolment, liveness nonce and liveness audit models.

face_enrolments       — one per user: the encrypted SFace template plus the exact
                        face-record PNG and signed receipt it came from (stored
                        unchanged so the record can be re-verified later).
used_liveness_nonces  — every accepted liveness receipt nonce; a receipt must
                        work only once (replay protection).
liveness_attempts     — audit trail of enrol / verify attempts. No images.

ON DELETE CASCADE: deleting a User removes all three.
"""

import uuid
from datetime import datetime, timezone
from typing import ClassVar

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlmodel import Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FaceEnrolment(SQLModel, table=True):
    __tablename__: ClassVar[str] = "face_enrolments"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            index=True,
            nullable=False,
        )
    )
    # Fernet-encrypted float32 SFace embedding
    template_enc: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # Exact face-record PNG bytes (112x112 aligned RGB) — never re-encode
    face_png: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    face_sha256: str
    receipt: str = Field(sa_column=Column(Text, nullable=False))
    face_quality: float
    model: str
    consent_at: datetime
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class UsedLivenessNonce(SQLModel, table=True):
    __tablename__: ClassVar[str] = "used_liveness_nonces"  # pyright: ignore[reportIncompatibleVariableOverride]

    nonce: str = Field(primary_key=True)
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    purpose: str
    created_at: datetime = Field(default_factory=_now)


class LivenessAttempt(SQLModel, table=True):
    __tablename__: ClassVar[str] = "liveness_attempts"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    nonce: str
    purpose: str                       # "enrol" | "verify"
    passed: bool
    fail_reason: str | None = Field(default=None)
    face_quality: float | None = Field(default=None)
    real_score: float | None = Field(default=None)
    match_score: float | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)
