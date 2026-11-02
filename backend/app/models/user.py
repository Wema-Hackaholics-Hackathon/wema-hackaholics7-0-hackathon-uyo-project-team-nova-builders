# pyright: ignore[reportImportCycles]
"""User account model."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .connected_bank import ConnectedBank  # pyright: ignore[reportImportCycles]
    from .consent import Consent  # pyright: ignore[reportImportCycles]
    from .credential import Credential  # pyright: ignore[reportImportCycles]
    from .ledger_entry import LedgerEntry  # pyright: ignore[reportImportCycles]
    from .notification import Notification  # pyright: ignore[reportImportCycles]
    from .refresh_token import RefreshToken  # pyright: ignore[reportImportCycles]
    from .wallet import Wallet  # pyright: ignore[reportImportCycles]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    first_name: str
    last_name: str
    middle_name: str | None = Field(default=None)
    # Nigerian National Identification Number — collected at signup, stored ENCRYPTED.
    # Set it only via app.services.user_identity.set_nin(). Never store or log it in plain text.
    nin_enc: str | None = Field(default=None)              # Fernet ciphertext (DATA_ENCRYPTION_KEY)
    nin_last4: str | None = Field(default=None)            # for display ("*******8901")
    # Keyed hash of the NIN (app.core.crypto.pii_hash) — lookups/matching without decrypting
    nin_hash: str | None = Field(default=None, index=True)
    # Collected during NIN verification (not at signup); YYYY-MM-DD
    date_of_birth: str | None = Field(default=None)
    # Set when the NIN was checked against the registry and name + DOB matched.
    # From then on first/middle/last name and date of birth are locked.
    nin_verified_at: datetime | None = Field(default=None)
    # Bank Verification Number — collected at KYC (optional until verified)
    bvn: str | None = Field(default=None, index=True)
    # Phone number — collected post-signup (optional until verified)
    phone: str | None = Field(default=None)
    # Residential address — editable by the user
    address: str | None = Field(default=None)
    # Proof of address — file path saved after uploading a utility bill (e.g. NEPA)
    proof_of_address_url: str | None = Field(default=None)
    # Profile picture — file path saved after uploading an avatar image
    avatar_url: str | None = Field(default=None)
    # Liveness face record — set to the authenticated GET /auth/me/liveness/face URL
    # once a face is enrolled (the PNG itself lives in face_enrolments)
    liveness_selfie_url: str | None = Field(default=None)
    # When the user last enrolled a face through a passed liveness check
    liveness_verified_at: datetime | None = Field(default=None)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    # Admin flag — only True for platform staff; set directly in the DB or via seeding
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)

    # ── Derived, read-only ─────────────────────────────────────────────────
    @property
    def nin(self) -> str:
        """Masked NIN for display/API output — the full number is never exposed."""
        return f"*******{self.nin_last4}" if self.nin_last4 else ""

    @property
    def identity_locked(self) -> bool:
        """Names and date of birth can't change once the NIN has been verified."""
        return self.nin_verified_at is not None

    # ── Relationships (navigate from User → children) ──────────────────────
    # Use lazy="selectin" so async sessions can load these without extra awaits.
    credential: Optional["Credential"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    wallet: Optional["Wallet"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    refresh_tokens: list["RefreshToken"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    notifications: list["Notification"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    connected_banks: list["ConnectedBank"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    consents: list["Consent"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    ledger_entries: list["LedgerEntry"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
