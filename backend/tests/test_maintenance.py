"""Housekeeping: dialect-neutral cleanup + full cascade of purged accounts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.config import _get_session_factory
from app.services.maintenance_service import run_cleanup
from tests.conftest import make_org, make_user, sql

OWNED = ("credentials", "wallets", "refresh_tokens", "email_verification_tokens", "notifications", "org_members")


async def test_cleanup_purges_stale_unverified_account_and_everything_it_owns(client: httpx.AsyncClient) -> None:
    stale = await make_user(client, verify_email=False)
    fresh = await make_user(client, verify_email=False)
    verified = await make_user(client)
    org = await make_org(client, stale)   # the stale user created an org → org survives, created_by cleared
    await sql("UPDATE users SET created_at=:t WHERE id=:u", t=datetime(2020, 1, 1), u=stale["id"])
    await sql("UPDATE users SET created_at=:t WHERE id=:u", t=datetime(2020, 1, 1), u=verified["id"])

    async with _get_session_factory()() as db:
        counts = await run_cleanup(db)
    assert counts["unverified_users"] >= 1

    assert await sql("SELECT 1 FROM users WHERE id=:u", u=stale["id"]) == []
    for table in OWNED:
        assert await sql(f"SELECT 1 FROM {table} WHERE user_id=:u", u=stale["id"]) == [], table
    assert await sql("SELECT created_by FROM organisations WHERE id=:o", o=org["id"]) == [(None,)]
    assert await sql("SELECT 1 FROM users WHERE id=:u", u=fresh["id"]) != []      # inside grace period
    assert await sql("SELECT 1 FROM users WHERE id=:u", u=verified["id"]) != []   # verified: kept


async def test_cleanup_removes_expired_tokens_and_old_idempotency_keys(client: httpx.AsyncClient) -> None:
    user = await make_user(client)
    await sql("UPDATE refresh_tokens SET expires_at=:t WHERE user_id=:u", t=datetime(2020, 1, 1), u=user["id"])
    async with _get_session_factory()() as db:
        await run_cleanup(db, now=datetime.now(timezone.utc) + timedelta(days=1))
    assert await sql("SELECT 1 FROM refresh_tokens WHERE user_id=:u", u=user["id"]) == []
    # raw SQL bypasses UTCDateTime, so pass naive UTC like the columns store
    an_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
    assert await sql("SELECT 1 FROM idempotency_records WHERE created_at < :t", t=an_hour_ago) == []
