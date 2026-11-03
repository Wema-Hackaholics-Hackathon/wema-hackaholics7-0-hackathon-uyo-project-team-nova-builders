"""Aggregate model imports — registers all tables on SQLModel.metadata.

This module must be imported before Alembic autogenerate or init_db() runs.
migrations/env.py does:  import app.models  # noqa: F401
app/config/__init__.py's init_db() also calls SQLModel.metadata.create_all,
which works because these imports have already registered all table classes.

Add new model imports here as they are created.
"""

from sqlmodel import SQLModel

from .business import (
    ApiKey,
    ApiRequestLog,
    AuditLog,
    CheckResult,
    ConsentGrant,
    IdempotencyRecord,
    Invoice,
    KybDocument,
    Organisation,
    OrgInvite,
    OrgMember,
    Subject,
    SubjectFace,
    UsageEvent,
    Verification,
    WebhookDelivery,
    WebhookEndpoint,
)
from .connected_bank import ConnectedBank
from .console import ConsoleNotification, ConsoleOtp, ConsoleRefreshToken, ConsoleUser
from .consent import Consent
from .credential import Credential, CredentialClaims, DEFAULT_CLAIMS
from .email_verification_token import EmailVerificationToken
from .face_enrolment import FaceEnrolment, LivenessAttempt, UsedLivenessNonce
from .ledger_entry import LedgerEntry
from .notification import Notification
from .password_reset_token import PasswordResetToken
from .refresh_token import RefreshToken
from .user import User
from .user_security import UserDevice, UserPasskey
from .wallet import Wallet, WalletTransaction

# Re-export everything so other modules can import from app.models directly
__all__ = [
    "SQLModel",
    "User",
    "UserDevice",
    "UserPasskey",
    "RefreshToken",
    "Credential",
    "CredentialClaims",
    "DEFAULT_CLAIMS",
    "EmailVerificationToken",
    "ConsoleUser",
    "ConsoleRefreshToken",
    "ConsoleOtp",
    "ConsoleNotification",
    "ApiKey",
    "ApiRequestLog",
    "AuditLog",
    "CheckResult",
    "ConsentGrant",
    "IdempotencyRecord",
    "Invoice",
    "KybDocument",
    "Organisation",
    "OrgMember",
    "OrgInvite",
    "Subject",
    "SubjectFace",
    "UsageEvent",
    "Verification",
    "WebhookDelivery",
    "WebhookEndpoint",
    "FaceEnrolment",
    "LivenessAttempt",
    "UsedLivenessNonce",
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

# All datetime columns: store naive UTC, return aware UTC (SQLite + Postgres).
from app.core.db_types import use_utc_datetimes  # noqa: E402

use_utc_datetimes(metadata)
