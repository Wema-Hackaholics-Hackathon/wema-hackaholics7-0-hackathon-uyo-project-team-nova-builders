"""Sign-in security for FOID user accounts: known devices (login alerts) and passkeys.

UserDevice   one row per browser/device the user has signed in from. A sign-in from a
             device not in this table triggers a "new sign-in" email + notification
             (when User.login_alerts is on). The device id is a random value the app
             keeps in localStorage; only its hash is stored.
UserPasskey  WebAuthn credentials ("Biometric unlock": Face ID, Touch ID, Windows Hello,
             Android fingerprint). Only the public key is stored — the private key never
             leaves the user's device.
"""

import uuid
from datetime import datetime, timezone
from typing import ClassVar

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlmodel import Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_fk() -> str:
    return Field(sa_column=Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))  # type: ignore[return-value]


class UserDevice(SQLModel, table=True):
    __tablename__: ClassVar[str] = "user_devices"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = _user_fk()
    device_hash: str = Field(index=True)          # sha256(user id + device id)
    user_agent: str | None = Field(default=None)
    ip: str | None = Field(default=None)          # last seen
    first_seen_at: datetime = Field(default_factory=_now)
    last_seen_at: datetime = Field(default_factory=_now)


class UserPasskey(SQLModel, table=True):
    __tablename__: ClassVar[str] = "user_passkeys"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = _user_fk()
    credential_id: str = Field(unique=True, index=True)   # base64url
    public_key: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    sign_count: int = Field(default=0)
    name: str = Field(default="Passkey")                  # e.g. "Chrome on Windows"
    created_at: datetime = Field(default_factory=_now)
    last_used_at: datetime | None = Field(default=None)
