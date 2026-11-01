# pyright: ignore[reportImportCycles]
"""Credential model — one per user, mutable state machine.

The `claims` column stores a JSON object matching the CredentialClaims
interface in frontend/src/types/foid.ts:

    {
        "identity_verified": bool,
        "bvn_validated": bool,
        "nin_verified": bool,
        "phone_verified": bool,
        "bill_verified": bool,
        "age_over_18": bool,
        "income_band": "low" | "mid" | "high",
        "account_stability": "stable" | "variable" | "poor",
        "repayment_reliability": "reliable" | "variable" | "poor"
    }

nin_verified, phone_verified, bill_verified are all False at signup
and can only be flipped to True by an admin via
PATCH /api/v1/admin/users/{user_id}/verifications.

Valid states (mirrors CredentialContext.tsx TRIGGER_EVENTS):
    active → under_review → downgraded → revoked

ON DELETE CASCADE: deleting a User removes their credential row.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Literal, Optional, TypedDict

from sqlalchemy import ForeignKey, JSON, String
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User  # pyright: ignore[reportImportCycles]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Typed representation of credential claims — mirrors frontend/src/types/foid.ts
class CredentialClaims(TypedDict):
    identity_verified: bool
    bvn_validated: bool
    # Admin-verified flags — only set to True by an admin
    nin_verified: bool
    phone_verified: bool
    bill_verified: bool       # proof-of-address (e.g. NEPA bill) verified
    # Email verification — True for all users during staging
    email_verified: bool
    age_over_18: bool
    income_band: Literal["low", "mid", "high"]
    account_stability: Literal["stable", "variable", "poor"]
    repayment_reliability: Literal["reliable", "variable", "poor"]


# Default claims for a freshly created credential.
# bvn_validated starts False — flipped via PATCH /auth/me/bvn.
# nin_verified / phone_verified / bill_verified start False — flipped by admin only.
# email_verified starts False — flipped to True via POST /auth/verify-email.
DEFAULT_CLAIMS: CredentialClaims = {
    "identity_verified": True,
    "bvn_validated": False,
    "nin_verified": False,
    "phone_verified": False,
    "bill_verified": False,
    "email_verified": False,
    "age_over_18": True,
    "income_band": "high",
    "account_stability": "stable",
    "repayment_reliability": "reliable",
}


class Credential(SQLModel, table=True):
    __tablename__: ClassVar[str] = "credentials"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    # One credential per user — enforced via unique constraint
    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            index=True,
            nullable=False,
        )
    )
    holder: str                          # full display name, e.g. "Daniel Afolabi"
    # State: active | under_review | downgraded | revoked
    state: str = Field(default="active")
    # JSON claims object — stored as JSON/JSONB column
    claims: CredentialClaims = Field(  # type: ignore[assignment]
        default_factory=lambda: dict(DEFAULT_CLAIMS),  # type: ignore[return-value]
        sa_column=Column(JSON, nullable=False),
    )
    issued_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # ── Relationship ────────────────────────────────────────────────────────
    user: Optional["User"] = Relationship(
        back_populates="credential",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
