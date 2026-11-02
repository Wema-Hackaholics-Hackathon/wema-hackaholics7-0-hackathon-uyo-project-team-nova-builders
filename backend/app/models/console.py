"""Business console accounts — separate from FOID user accounts.

A person who runs a business on FOID signs in to the console (enterprise/) with a
console account, even if the same person also has a FOID user account. The two
never share sessions, tokens or passwords: console access tokens carry
`type="console"`, which the user app rejects, and user tokens are rejected here.

ConsoleUser ── org_members (role per organisation)
            ── console_refresh_tokens (hashed, rotated on refresh)
            ── console_otps (email verification + password reset codes, hashed)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from sqlalchemy import ForeignKey, String
from sqlmodel import Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _console_user_fk() -> Any:
    return Field(sa_column=Column(String, ForeignKey("console_users.id", ondelete="CASCADE"), index=True, nullable=False))


class ConsoleUser(SQLModel, table=True):
    __tablename__: ClassVar[str] = "console_users"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    first_name: str
    last_name: str
    email: str = Field(unique=True, index=True)   # stored lower-cased
    hashed_password: str
    email_verified_at: datetime | None = Field(default=None)
    # Two-step sign-in (TOTP, core/totp.py). Secret is Fernet-encrypted; enabled once a code was confirmed.
    totp_secret_enc: str | None = Field(default=None)
    totp_enabled_at: datetime | None = Field(default=None)
    totp_last_step: int | None = Field(default=None)   # last accepted 30 s step — a code works once
    last_active_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


class ConsoleRefreshToken(SQLModel, table=True):
    __tablename__: ClassVar[str] = "console_refresh_tokens"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    console_user_id: str = _console_user_fk()
    token_hash: str = Field(unique=True, index=True)   # SHA-256, never the raw token
    expires_at: datetime
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class ConsoleOtp(SQLModel, table=True):
    __tablename__: ClassVar[str] = "console_otps"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    console_user_id: str = _console_user_fk()
    purpose: str                    # verify_email | reset_password
    code_hash: str                  # SHA-256 of the 6-digit code
    expires_at: datetime
    attempts: int = Field(default=0)
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class ConsoleNotification(SQLModel, table=True):
    """The console bell: one row per team member, so read/unread is personal. Created by services/console_inbox.py."""
    __tablename__: ClassVar[str] = "console_notifications"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(sa_column=Column(String, ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False))
    console_user_id: str = _console_user_fk()
    kind: str                       # kyb_approved | invoice_paid | webhook_failing | … (see console_inbox)
    title: str
    body: str = Field(default="")
    link: str | None = Field(default=None)     # console path to open, e.g. /go-live
    ref: str | None = Field(default=None)      # what it's about (e.g. webhook endpoint id) — used to avoid repeats
    read_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now, index=True)
