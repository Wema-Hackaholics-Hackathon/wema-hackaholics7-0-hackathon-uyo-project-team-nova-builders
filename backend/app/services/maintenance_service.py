"""Periodic housekeeping (run by the cleanup loop in main.py). Dialect-neutral ORM only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.cascade import delete_cascade
from app.models import Credential, EmailVerificationToken, IdempotencyRecord, PasswordResetToken, RefreshToken, User

UNVERIFIED_GRACE_DAYS = 3
IDEMPOTENCY_TTL = timedelta(hours=24)


async def run_cleanup(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Purge expired/used tokens, stale idempotency keys and never-verified accounts. Commits."""
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    async def purge(statement: Any) -> int:
        return cast(CursorResult[Any], await db.execute(statement)).rowcount or 0

    counts["refresh_tokens"] = await purge(delete(RefreshToken).where(
        or_(col(RefreshToken.revoked).is_(True), col(RefreshToken.expires_at) < now)))
    counts["password_reset_tokens"] = await purge(delete(PasswordResetToken).where(
        or_(col(PasswordResetToken.used).is_(True), col(PasswordResetToken.expires_at) < now)))
    counts["email_verification_tokens"] = await purge(delete(EmailVerificationToken).where(
        or_(col(EmailVerificationToken.used).is_(True), col(EmailVerificationToken.expires_at) < now)))
    counts["idempotency_records"] = await purge(delete(IdempotencyRecord).where(
        col(IdempotencyRecord.created_at) < now - IDEMPOTENCY_TTL))

    # Accounts whose email was never verified within the grace period — with everything they own.
    cutoff = now - timedelta(days=UNVERIFIED_GRACE_DAYS)
    rows = (await db.exec(
        select(User.id, Credential.claims)
        .join(Credential, col(Credential.user_id) == col(User.id), isouter=True)
        .where(col(User.created_at) < cutoff)
    )).all()
    stale = [uid for uid, claims in rows if not (claims or {}).get("email_verified")]
    counts["unverified_users"] = await delete_cascade(db, "users", stale)

    await db.commit()
    return counts
