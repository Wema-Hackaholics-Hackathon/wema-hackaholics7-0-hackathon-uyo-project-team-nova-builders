"""Login messages and the out-of-date-schema guard."""

from __future__ import annotations

import httpx
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.schema_check import check_schema, head_revision
from tests.conftest import make_user


async def test_login_says_which_part_is_wrong(client: httpx.AsyncClient) -> None:
    user = await make_user(client)
    r = await client.post("/api/v1/auth/login", json={"email": "nobody-here@example.com", "password": "Passw0rd!x"})
    assert r.status_code == 404 and r.json()["detail"] == "No account exists with this email address"
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Wrong0rd!x"})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect password"
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Passw0rd!x"})
    assert r.status_code == 200


async def test_signup_rejects_short_nin(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/auth/signup", json=dict(first_name="A", last_name="B", nin="123",
                                                          email="short-nin@example.com", password="Passw0rd!x"))
    assert r.status_code == 422 and "NIN must be exactly 11 digits" in r.text


async def test_schema_check(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/s.db")
    # fresh DB → stamped at head
    status = await check_schema(engine, was_empty=True)
    assert status.ok and status.db_revision == head_revision()
    # DB behind the code → not ok, with the command to run
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("UPDATE alembic_version SET version_num='e5f6a7b8c9d0'"))
    status = await check_schema(engine, was_empty=False)
    assert not status.ok and "alembic upgrade head" in (status.message or "")
    await engine.dispose()


# ---------------------------------------------------------------------------
# NIN: encrypted at rest, verified (paid lookup) only after liveness, then locked
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

from tests.conftest import sql  # noqa: E402

VERIFY = "/api/v1/auth/me/nin/verify"
DOB = "1995-04-12"


async def _passed_liveness(user: dict) -> None:  # type: ignore[type-arg]
    await sql("UPDATE users SET liveness_verified_at=:t WHERE id=:u", t=datetime(2026, 1, 1), u=user["id"])


async def test_nin_is_encrypted_at_rest_and_masked(client: httpx.AsyncClient) -> None:
    user = await make_user(client, nin="81234567890")
    row = (await sql("SELECT nin_enc, nin_last4, nin_hash FROM users WHERE id=:u", u=user["id"]))[0]
    assert "81234567890" not in str(row) and row[1] == "7890" and row[0].startswith("gAAAA")
    me = (await client.get("/api/v1/auth/me", headers=user["headers"])).json()
    assert me["nin"] == "*******7890" and me["identity_locked"] is False


async def test_nin_verification_requires_liveness_first(client: httpx.AsyncClient) -> None:
    user = await make_user(client, nin="81234567891")
    r = await client.post(VERIFY, headers=user["headers"],
                          json={"first_name": "Ada", "last_name": "Obi", "date_of_birth": DOB})
    assert r.status_code == 409 and "liveness" in r.json()["detail"]


async def test_nin_verification_failures(client: httpx.AsyncClient) -> None:
    body = {"first_name": "Ada", "last_name": "Obi", "date_of_birth": DOB}
    for nin, expected in (("81234567899", "couldn't find a record"), ("81234567898", "doesn't match")):
        user = await make_user(client, nin=nin)
        await _passed_liveness(user)
        r = await client.post(VERIFY, headers=user["headers"], json=body)
        assert r.status_code == 422 and expected in r.json()["detail"], r.text
    r = await client.post(VERIFY, headers=user["headers"], json={**body, "date_of_birth": "2999-01-01"})
    assert r.status_code == 422   # future DOB rejected by validation


async def test_nin_verified_then_identity_locked(client: httpx.AsyncClient) -> None:
    user = await make_user(client, nin="81234567892")
    await _passed_liveness(user)
    r = await client.post(VERIFY, headers=user["headers"],
                          json={"first_name": "Adaeze", "middle_name": "Ngozi", "last_name": "Obi", "date_of_birth": DOB})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["identity_locked"] is True and me["date_of_birth"] == DOB and me["first_name"] == "Adaeze"
    claims = (await client.get("/api/v1/credentials/me", headers=user["headers"])).json()["claims"]
    assert claims["nin_verified"] is True
    # locked: names / DOB can't be changed by verifying again
    r = await client.post(VERIFY, headers=user["headers"],
                          json={"first_name": "Someone", "last_name": "Else", "date_of_birth": "1990-01-01"})
    assert r.status_code == 409
    me = (await client.get("/api/v1/auth/me", headers=user["headers"])).json()
    assert me["first_name"] == "Adaeze" and me["date_of_birth"] == DOB

    # one verified account per NIN
    other = await make_user(client, nin="81234567892", email="second-claim@example.com")
    await _passed_liveness(other)
    r = await client.post(VERIFY, headers=other["headers"],
                          json={"first_name": "Ada", "last_name": "Obi", "date_of_birth": DOB})
    assert r.status_code == 409 and "another FOID account" in r.json()["detail"]


async def test_nin_verification_attempt_limit(client: httpx.AsyncClient) -> None:
    user = await make_user(client, nin="81234567899")   # always "not found"
    await _passed_liveness(user)
    body = {"first_name": "Ada", "last_name": "Obi", "date_of_birth": DOB}
    for _ in range(5):
        assert (await client.post(VERIFY, headers=user["headers"], json=body)).status_code == 422
    r = await client.post(VERIFY, headers=user["headers"], json=body)
    assert r.status_code == 429


# ── BVN: verified against the registry, stored encrypted, never returned in full ──

BVN = "/api/v1/auth/me/bvn"


async def _nin_verified(client: httpx.AsyncClient, nin: str) -> dict:  # type: ignore[type-arg]
    user = await make_user(client, nin=nin)
    await _passed_liveness(user)
    r = await client.post(VERIFY, headers=user["headers"], json={"first_name": "Ada", "last_name": "Obi", "date_of_birth": DOB})
    assert r.status_code == 200, r.text
    return user


async def test_bvn_needs_verified_nin_and_a_registry_match(client: httpx.AsyncClient) -> None:
    fresh = await make_user(client, nin="81234567893")
    r = await client.patch(BVN, headers=fresh["headers"], json={"bvn": "22345678901"})
    assert r.status_code == 409 and "Verify your NIN first" in r.json()["detail"]

    user = await _nin_verified(client, "81234567894")
    for bvn, expected in (("22345678909", "couldn't find a record"), ("22345678908", "doesn't match")):
        r = await client.patch(BVN, headers=user["headers"], json={"bvn": bvn})
        assert r.status_code == 422 and expected in r.json()["detail"], r.text
    row = (await sql("SELECT bvn_enc, bvn_last4, bvn_verified_at FROM users WHERE id=:u", u=user["id"]))[0]
    assert row == (None, None, None)                                     # nothing kept for a failed BVN
    claims = (await client.get("/api/v1/credentials/me", headers=user["headers"])).json()["claims"]
    assert claims["bvn_validated"] is False

    r = await client.patch(BVN, headers=user["headers"], json={"bvn": "22345678901"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["bvn"] == "*******8901" and me["bvn_verified_at"]
    assert "22345678901" not in r.text and "22345678901" not in (await client.get("/api/v1/auth/me", headers=user["headers"])).text
    row = (await sql("SELECT bvn_enc, bvn_last4 FROM users WHERE id=:u", u=user["id"]))[0]
    assert row[0].startswith("gAAAA") and "22345678901" not in str(row) and row[1] == "8901"
    claims = (await client.get("/api/v1/credentials/me", headers=user["headers"])).json()["claims"]
    assert claims["bvn_validated"] is True
    assert (await client.patch(BVN, headers=user["headers"], json={"bvn": "22345678902"})).status_code == 409

    other = await _nin_verified(client, "81234567895")
    r = await client.patch(BVN, headers=other["headers"], json={"bvn": "22345678901"})
    assert r.status_code == 422 and "another FOID account" in r.json()["detail"]
