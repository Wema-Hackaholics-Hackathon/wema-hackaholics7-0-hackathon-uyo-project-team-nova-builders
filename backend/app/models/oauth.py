"""'Continue with FOID' apps — OAuth clients a business registers in the console.

OAuthApp           one per business per env (test | live): client id (public), allowed browser origins,
                   exact redirect URIs, the scopes it may ask for, and how it proves itself on the code
                   exchange (client secret, or private_key_jwt with a public key we hold).
OAuthClientSecret  hashed secrets for an app (foid_cs_test_… / foid_cs_live_…), shown once. Rotating
                   gives the old secret 24 h (expires_at) so deployments can switch over.

See docs/continue-with-foid.md.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from sqlalchemy import JSON, ForeignKey, String
from sqlmodel import Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OAuthApp(SQLModel, table=True):
    __tablename__: ClassVar[str] = "oauth_apps"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    org_id: str = Field(sa_column=Column(String, ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False))
    env: str                                          # test | live
    name: str
    client_id: str = Field(unique=True, index=True)   # foid_app_test_… — public
    origins: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))        # for the popup (postMessage)
    redirect_uris: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # exact match
    scopes: list[str] = Field(default_factory=lambda: ["profile"], sa_column=Column(JSON, nullable=False))
    auth_method: str = Field(default="client_secret")  # client_secret | private_key_jwt
    public_jwk: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_by: str | None = Field(default=None)       # console_users.id
    created_at: datetime = Field(default_factory=_now)
    disabled_at: datetime | None = Field(default=None)


class OAuthClientSecret(SQLModel, table=True):
    __tablename__: ClassVar[str] = "oauth_client_secrets"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    app_id: str = Field(sa_column=Column(String, ForeignKey("oauth_apps.id", ondelete="CASCADE"), index=True, nullable=False))
    hint: str                                        # foid_cs_test_Ab…9z
    secret_hash: str = Field(unique=True, index=True)
    created_by: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime | None = Field(default=None)  # set on rotation: old secret keeps working until then
    revoked_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)


class OAuthRequest(SQLModel, table=True):
    """One 'Continue with FOID' attempt: from the popup opening to the business exchanging the code.

    status: pending → approved (code issued) → exchanged | denied | revoked (code replayed) | expired
    """
    __tablename__: ClassVar[str] = "oauth_requests"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    app_id: str = Field(sa_column=Column(String, ForeignKey("oauth_apps.id", ondelete="CASCADE"), index=True, nullable=False))
    org_id: str = Field(index=True)
    env: str
    response_mode: str                       # web_message (popup → postMessage) | query (redirect)
    origin: str | None = Field(default=None)        # web_message: where the result is posted
    redirect_uri: str | None = Field(default=None)  # query: where the browser is sent
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    state: str
    nonce: str | None = Field(default=None)
    code_challenge: str                      # PKCE S256
    status: str = Field(default="pending", index=True)
    # email one-time code (sign-in inside the popup)
    email: str | None = Field(default=None)
    otp_hash: str | None = Field(default=None)
    otp_expires_at: datetime | None = Field(default=None)
    otp_attempts: int = Field(default=0)
    otp_sends: int = Field(default=0)
    # who approved, and what it produced
    user_id: str | None = Field(default=None, index=True)
    verification_id: str | None = Field(default=None)   # new person: the hosted verification used
    subject_id: str | None = Field(default=None)
    grant_id: str | None = Field(default=None)
    rematched_at: datetime | None = Field(default=None)
    # one-time code for the business's server
    code_hash: str | None = Field(default=None, unique=True, index=True)
    code_expires_at: datetime | None = Field(default=None)
    code_used_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime
