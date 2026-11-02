"""Business platform models — organisations using the FOID Open API.

Organisation ── members (FOID users with a role)
             ── api_keys (sk_test_/sk_live_, stored hashed)
             ── webhook_endpoints ── webhook_deliveries
             ── subjects (the business's customers; may or may not be FOID users)
                   ── consent_grants (what the subject allowed this business to see)
                   ── verifications (hosted flows) ── check_results
                   ── subject_faces (liveness face for re-verification)

A Subject belongs to ONE organisation. The same person verified by two
businesses is two Subject rows. If that person has (or later creates) a FOID
account, each Subject is linked to the User via subjects.user_id — see
services/subject_link_service.py for the linking rules.

All tables cascade from organisations; subject-owned rows cascade from subjects.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from sqlalchemy import JSON, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _org_fk() -> Any:
    return Field(sa_column=Column(String, ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False))


def _subject_fk(nullable: bool = False) -> Any:
    return Field(
        default=None if nullable else ...,
        sa_column=Column(String, ForeignKey("subjects.id", ondelete="CASCADE"), index=True, nullable=nullable),
    )


# ---------------------------------------------------------------------------
# Organisation, members, keys
# ---------------------------------------------------------------------------

class Organisation(SQLModel, table=True):
    __tablename__: ClassVar[str] = "organisations"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    website: str | None = Field(default=None)
    support_email: str | None = Field(default=None)
    # Branding shown on the hosted verification page (next to "Secured by FOID")
    logo_url: str | None = Field(default=None)
    brand_color: str | None = Field(default=None)
    # KYB — live keys only once FOID approves the business
    rc_number: str | None = Field(default=None)
    kyb_status: str = Field(default="not_submitted")   # not_submitted | pending | approved | rejected
    live_enabled: bool = Field(default=False)
    status: str = Field(default="active")              # active | suspended
    created_by: str = Field(sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    created_at: datetime = Field(default_factory=_now)


class OrgMember(SQLModel, table=True):
    __tablename__: ClassVar[str] = "org_members"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    user_id: str = Field(sa_column=Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))
    role: str = Field(default="viewer")   # owner | admin | developer | reviewer | viewer
    created_at: datetime = Field(default_factory=_now)


class ApiKey(SQLModel, table=True):
    __tablename__: ClassVar[str] = "api_keys"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str                      # test | live
    name: str = Field(default="Default key")
    prefix: str                   # first characters, shown in the dashboard (sk_test_AbC…)
    key_hash: str = Field(unique=True, index=True)
    created_by: str | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

class WebhookEndpoint(SQLModel, table=True):
    __tablename__: ClassVar[str] = "webhook_endpoints"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    url: str
    secret_enc: str               # Fernet-encrypted whsec_… signing secret
    events: list[str] = Field(default_factory=lambda: ["*"], sa_column=Column(JSON, nullable=False))
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now)


class WebhookDelivery(SQLModel, table=True):
    __tablename__: ClassVar[str] = "webhook_deliveries"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    endpoint_id: str = Field(sa_column=Column(String, ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False))
    event_id: str = Field(index=True)
    event_type: str
    # Subject the event is about — deliveries are cancelled if consent is revoked
    subject_id: str | None = Field(default=None, index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)   # pending | delivered | failed | cancelled
    attempts: int = Field(default=0)
    next_attempt_at: datetime = Field(default_factory=_now)
    last_status_code: int | None = Field(default=None)
    last_error: str | None = Field(default=None)
    delivered_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Subjects, consent, verifications
# ---------------------------------------------------------------------------

class Subject(SQLModel, table=True):
    __tablename__: ClassVar[str] = "subjects"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    customer_ref: str | None = Field(default=None, index=True)   # the business's own id for this person
    first_name: str | None = Field(default=None)
    middle_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    date_of_birth: str | None = Field(default=None)               # YYYY-MM-DD
    email: str | None = Field(default=None, index=True)
    phone: str | None = Field(default=None)
    # Identifiers: keyed hash for matching + last 4 for display. Raw numbers are not stored.
    nin_hash: str | None = Field(default=None, index=True)
    nin_last4: str | None = Field(default=None)
    nin_verified: bool = Field(default=False)
    bvn_hash: str | None = Field(default=None, index=True)
    bvn_last4: str | None = Field(default=None)
    bvn_verified: bool = Field(default=False)
    liveness_passed_at: datetime | None = Field(default=None)
    # Link to a FOID account (set by subject_link_service)
    user_id: str | None = Field(
        default=None,
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True),
    )
    linked_at: datetime | None = Field(default=None)
    link_method: str | None = Field(default=None)   # foid_share | email_nin | face_nin
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ConsentGrant(SQLModel, table=True):
    """What a subject allowed one organisation to access. Revocation stops all data flow."""

    __tablename__: ClassVar[str] = "consent_grants"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    subject_id: str = _subject_fk()
    user_id: str | None = Field(
        default=None,
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True),
    )
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    purpose: str
    # hosted_flow: the person accepted on FOID's page.
    # business_attested: the business called a check API and attests it collected consent itself.
    source: str
    status: str = Field(default="active", index=True)   # active | revoked
    consent_text_version: str = Field(default="2026-11-01")
    ip: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)
    granted_at: datetime = Field(default_factory=_now)
    revoked_at: datetime | None = Field(default=None)
    revoked_by: str | None = Field(default=None)   # user | business | admin


class Verification(SQLModel, table=True):
    __tablename__: ClassVar[str] = "verifications"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    subject_id: str = _subject_fk()
    checks: list[str] = Field(sa_column=Column(JSON, nullable=False))
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    purpose: str
    status: str = Field(default="pending", index=True)   # pending | in_progress | completed | cancelled | expired
    outcome: str | None = Field(default=None)            # passed | failed | needs_review
    session_token_hash: str = Field(unique=True, index=True)
    # Fernet-encrypted token, so the business can fetch the hosted link again while it's open
    session_token_enc: str | None = Field(default=None)
    return_url: str | None = Field(default=None)
    reused_foid_credential: bool = Field(default=False)
    metadata_: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSON, nullable=False))
    expires_at: datetime
    completed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


class CheckResult(SQLModel, table=True):
    __tablename__: ClassVar[str] = "check_results"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    subject_id: str = _subject_fk()
    verification_id: str | None = Field(
        default=None,
        sa_column=Column(String, ForeignKey("verifications.id", ondelete="CASCADE"), index=True, nullable=True),
    )
    type: str                         # nin | bvn | liveness | reverify
    status: str                       # passed | failed | needs_review | error
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    provider: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


class SubjectFace(SQLModel, table=True):
    """Liveness face record of a subject, for later re-verification (encrypted template)."""

    __tablename__: ClassVar[str] = "subject_faces"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    subject_id: str = Field(
        sa_column=Column(String, ForeignKey("subjects.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    )
    template_enc: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    face_png: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    face_sha256: str
    receipt: str = Field(sa_column=Column(Text, nullable=False))
    face_quality: float
    model: str
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Plumbing: idempotency, usage (billing), audit
# ---------------------------------------------------------------------------

class IdempotencyRecord(SQLModel, table=True):
    __tablename__: ClassVar[str] = "idempotency_records"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (UniqueConstraint("org_id", "env", "key"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    key: str
    request_hash: str
    status_code: int
    response: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_now)


class UsageEvent(SQLModel, table=True):
    __tablename__: ClassVar[str] = "usage_events"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = _org_fk()
    env: str
    check_type: str
    subject_id: str | None = Field(default=None)
    verification_id: str | None = Field(default=None)
    billable: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now, index=True)


class AuditLog(SQLModel, table=True):
    __tablename__: ClassVar[str] = "audit_logs"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str | None = Field(default=None, index=True)
    actor_type: str                   # user | api_key | subject | system
    actor_id: str | None = Field(default=None)
    action: str                       # e.g. api_key.created, consent.revoked, subject.deleted
    target_type: str | None = Field(default=None)
    target_id: str | None = Field(default=None)
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    ip: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now, index=True)
