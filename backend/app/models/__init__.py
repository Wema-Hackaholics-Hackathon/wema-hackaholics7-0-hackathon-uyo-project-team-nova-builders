"""Aggregate model imports — registers all tables on SQLModel.metadata.

This module must be imported before Alembic autogenerate or init_db() runs.
migrations/env.py does:  import app.models  # noqa: F401
app/config/__init__.py's init_db() also calls SQLModel.metadata.create_all,
which works because these imports have already registered all table classes.

Add new model imports here as they are created.
"""

from sqlmodel import SQLModel

from .connected_bank import ConnectedBank
from .consent import Consent
from .credential import Credential, CredentialClaims, DEFAULT_CLAIMS
from .email_verification_token import EmailVerificationToken
from .ledger_entry import LedgerEntry
from .liveness_session import LivenessSession
from .notification import Notification
from .password_reset_token import PasswordResetToken
from .refresh_token import RefreshToken
from .user import User
from .wallet import Wallet, WalletTransaction

# Re-export everything so other modules can import from app.models directly
__all__ = [
    "SQLModel",
    "User",
    "RefreshToken",
    "Credential",
    "CredentialClaims",
    "DEFAULT_CLAIMS",
    "EmailVerificationToken",
    "LivenessSession",
    "Notification",
    "ConnectedBank",
    "Consent",
    "LedgerEntry",
    "PasswordResetToken",
    "Wallet",
    "WalletTransaction",
    "metadata",
]

metadata = SQLModel.metadata
