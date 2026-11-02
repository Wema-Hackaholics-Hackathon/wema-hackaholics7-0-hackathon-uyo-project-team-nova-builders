"""A FOID user's own NIN: encrypted storage and registry verification.

The NIN collected at signup is only a *claim*. It is stored encrypted
(Fernet, DATA_ENCRYPTION_KEY) with a keyed hash for lookups and the last 4
digits for display — never in plain text.

Paid registry verification (verify_nin) runs only after the email is verified
and the liveness check passed, so we don't pay to check throwaway accounts.
It compares the names and date of birth on the account with the NIN record;
on a match the claim nin_verified flips and the identity (names + DOB) locks.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.crypto import decrypt_str, encrypt_str, pii_hash
from app.models import AuditLog, Credential, Notification, User
from app.services.identity import IdentityProvider, get_provider
from app.services.identity.base import match_record
from app.services.identity.mock import MockProvider

MAX_ATTEMPTS_PER_DAY = 5


def set_nin(user: User, nin: str) -> None:
    nin = nin.strip()
    user.nin_enc = encrypt_str(nin)
    user.nin_hash = pii_hash(nin)
    user.nin_last4 = nin[-4:]


def get_nin(user: User) -> str | None:
    """Decrypt — only for the registry lookup itself. Don't return or log the result."""
    return decrypt_str(user.nin_enc) if user.nin_enc else None


def validate_dob(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise ValueError("Date of birth must be YYYY-MM-DD")
    d = date.fromisoformat(value)
    if not date(1900, 1, 1) <= d <= date.today():
        raise ValueError("Date of birth is out of range")
    return value


def first_party_provider() -> IdentityProvider:
    """Real provider in production; the sandbox mock everywhere else."""
    if get_settings().ENV == "production":
        return get_provider("live")
    return MockProvider()


@dataclass
class NinVerification:
    verified: bool
    reasons: list[str]


async def attempts_today(db: AsyncSession, user: User) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    rows = (await db.exec(select(AuditLog.id).where(
        AuditLog.actor_id == user.id, AuditLog.action == "nin.verify_attempt", col(AuditLog.created_at) >= since,
    ))).all()
    return len(rows)


async def nin_taken_by_other(db: AsyncSession, user: User) -> bool:
    other = (await db.exec(select(User.id).where(
        User.nin_hash == user.nin_hash, User.id != user.id, col(User.nin_verified_at).is_not(None),
    ))).first()
    return other is not None


async def verify_nin(db: AsyncSession, user: User) -> NinVerification:
    """Look the NIN up and match names + DOB. Caller has applied the submitted names/DOB. Caller commits."""
    nin = get_nin(user)
    if not nin:
        return NinVerification(False, ["no_nin_on_account"])
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="nin.verify_attempt"))

    provider = first_party_provider()
    if isinstance(provider, MockProvider):
        provider.expect(user.first_name, user.middle_name, user.last_name, user.date_of_birth)
    record = await provider.lookup_nin(nin)   # ProviderUnavailable propagates to the router
    if not record.found:
        return NinVerification(False, ["not_found"])

    match = match_record(record, user.first_name, user.last_name, user.middle_name, user.date_of_birth)
    reasons = []
    if not match.name_match:
        reasons.append("name_mismatch")
    if match.dob_match is not True:
        reasons.append("dob_mismatch")
    if reasons:
        db.add(AuditLog(actor_type="user", actor_id=user.id, action="nin.verify_failed", meta={"reasons": reasons}))
        return NinVerification(False, reasons)

    user.nin_verified_at = datetime.now(timezone.utc)
    db.add(user)
    cred = (await db.exec(select(Credential).where(Credential.user_id == user.id))).first()
    if cred is not None:
        cred.claims = {**cred.claims, "nin_verified": True}  # type: ignore[assignment]
        cred.updated_at = datetime.now(timezone.utc)
        db.add(cred)
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="NIN verified",
        change="nin_verified: False → True",
        reason="Your name and date of birth match your NIN record.",
        action="Your name and date of birth are now locked to your verified identity.",
    ))
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="nin.verified"))
    return NinVerification(True, [])
