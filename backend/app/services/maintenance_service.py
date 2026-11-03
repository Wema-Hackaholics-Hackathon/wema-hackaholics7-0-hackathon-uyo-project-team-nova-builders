"""Periodic housekeeping (run by the cleanup loop in main.py). Dialect-neutral ORM only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.cascade import delete_cascade
from app.models import (
    ApiRequestLog,
    ConsoleNotification,
    ConsoleOtp,
    ConsoleRefreshToken,
    Credential,
    EmailVerificationToken,
    IdempotencyRecord,
    OAuthRequest,
    Organisation,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.services.request_log_service import cutoff as request_log_cutoff

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
    counts["console_refresh_tokens"] = await purge(delete(ConsoleRefreshToken).where(
        or_(col(ConsoleRefreshToken.revoked).is_(True), col(ConsoleRefreshToken.expires_at) < now)))
    counts["console_otps"] = await purge(delete(ConsoleOtp).where(
        or_(col(ConsoleOtp.used).is_(True), col(ConsoleOtp.expires_at) < now)))
    # Continue with FOID requests: the consent grant is the lasting record; the request is bookkeeping
    counts["oauth_requests"] = await purge(delete(OAuthRequest).where(
        col(OAuthRequest.created_at) < now - timedelta(days=7)))
    counts["console_notifications"] = await purge(delete(ConsoleNotification).where(
        col(ConsoleNotification.created_at) < now - timedelta(days=90)))
    counts["api_request_logs"] = await purge(delete(ApiRequestLog).where(
        col(ApiRequestLog.created_at) < request_log_cutoff(now)))   # 30-day retention

    # Accounts whose email was never verified within the grace period — with everything they own.
    cutoff = now - timedelta(days=UNVERIFIED_GRACE_DAYS)
    rows = (await db.exec(
        select(User.id, Credential.claims)
        .join(Credential, col(Credential.user_id) == col(User.id), isouter=True)
        .where(col(User.created_at) < cutoff)
    )).all()
    stale = [uid for uid, claims in rows if not (claims or {}).get("email_verified")]
    counts["unverified_users"] = await delete_cascade(db, "users", stale)

    gone = (await db.exec(select(Organisation.id).where(Organisation.status == "suspended",
                                                        col(Organisation.deactivated_at) < now - timedelta(days=30)))).all()
    counts["deactivated_organisations"] = await delete_cascade(db, "organisations", list(gone))

    await db.commit()
    from app.services.billing_service import open_renewals
    counts["renewal_invoices"] = await open_renewals(db, now)
    return counts
