"""Business console accounts (separate from FOID users) and API key handling."""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from app.routers import console_auth
from tests.conftest import make_member, make_org, make_user, sql

AUTH = "/api/v1/console/auth"
BIZ = "/api/v1/business"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Codes emailed by the console (instead of sending)."""
    sent: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append(re.findall(r"\b\d{6}\b", body)[-1])

    monkeypatch.setattr(console_auth, "send_email", fake_send)
    return sent


async def test_signup_creates_org_and_needs_verified_email(client: httpx.AsyncClient, outbox: list[str]) -> None:
    r = await client.post(f"{AUTH}/signup", json=dict(first_name="Ada", last_name="Nwosu", email="Ada@Sterling.example",
                                                       password="Passw0rd!x", company_name="Sterling MFB"))
    assert r.status_code == 201
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get(f"{AUTH}/me", headers=h)).json()
    assert me["email"] == "ada@sterling.example" and me["email_verified"] is False

    r = await client.get(f"{BIZ}/organisations", headers=h)
    assert r.status_code == 403                                    # verify first

    assert (await client.post(f"{AUTH}/verify-email", json={"code": "000000" if outbox[0] != "000000" else "111111"},
                              headers=h)).status_code == 400
    r = await client.post(f"{AUTH}/verify-email", json={"code": outbox[0]}, headers=h)
    assert r.status_code == 200 and r.json()["email_verified"] is True

    orgs = (await client.get(f"{BIZ}/organisations", headers=h)).json()
    assert [(o["name"], o["role"], o["kyb_status"]) for o in orgs] == [("Sterling MFB", "owner", "not_submitted")]

    r = await client.post(f"{AUTH}/signup", json=dict(first_name="A", last_name="B", email="ada@sterling.example",
                                                       password="Passw0rd!x", company_name="Again"))
    assert r.status_code == 409


async def test_console_and_user_sessions_are_separate(client: httpx.AsyncClient) -> None:
    person = await make_user(client, email="same@person.example")
    member = await make_member(client, email="same@person.example")   # same email, separate account

    assert (await client.get(f"{AUTH}/me", headers=person["headers"])).status_code == 401
    assert (await client.get(f"{BIZ}/organisations", headers=person["headers"])).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=member["headers"])).status_code == 401

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": member["refresh_token"]})
    assert r.status_code == 401                                    # console refresh token means nothing to the user app


async def test_login_refresh_logout(client: httpx.AsyncClient) -> None:
    m = await make_member(client)
    assert (await client.post(f"{AUTH}/login", json={"email": "nobody@biz.example", "password": "x"})).status_code == 404
    assert (await client.post(f"{AUTH}/login", json={"email": m["email"], "password": "Wrong0!pass"})).status_code == 401
    r = await client.post(f"{AUTH}/login", json={"email": m["email"].upper(), "password": "Passw0rd!x"})
    assert r.status_code == 200
    first = r.json()["refresh_token"]

    r = await client.post(f"{AUTH}/refresh", json={"refresh_token": first})
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": first})).status_code == 401   # rotated

    assert (await client.post(f"{AUTH}/logout", json={"refresh_token": second})).status_code == 204
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": second})).status_code == 401


async def test_password_reset_limits_tries_and_signs_out(client: httpx.AsyncClient, outbox: list[str]) -> None:
    m = await make_member(client)
    outbox.clear()
    assert (await client.post(f"{AUTH}/forgot-password", json={"email": "ghost@biz.example"})).status_code == 200
    assert outbox == []                                            # no account → nothing sent, same answer
    await client.post(f"{AUTH}/forgot-password", json={"email": m["email"]})
    code = outbox[-1]
    wrong = "000000" if code != "000000" else "111111"
    body: dict[str, Any] = {"email": m["email"], "new_password": "N3w!passw0rd"}
    for _ in range(5):
        assert (await client.post(f"{AUTH}/reset-password", json={**body, "code": wrong})).status_code == 400
    assert (await client.post(f"{AUTH}/reset-password", json={**body, "code": code})).status_code == 400   # burned

    await client.post(f"{AUTH}/forgot-password", json={"email": m["email"]})
    assert (await client.post(f"{AUTH}/reset-password", json={**body, "code": outbox[-1]})).status_code == 204
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": m["refresh_token"]})).status_code == 401
    assert (await client.post(f"{AUTH}/login", json={"email": m["email"], "password": "N3w!passw0rd"})).status_code == 200


async def test_api_key_shown_once_and_only_hint_stored(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    for env, raw in org["keys"].items():
        assert re.fullmatch(rf"FOID_{env.upper()}_[A-Za-z0-9]{{40}}", raw)
        assert (await client.get("/api/open/v1/ping", headers=org["h"][env])).json()["env"] == env

    listed = (await client.get(f"{BIZ}/organisations/{org['id']}/api-keys", headers=owner["headers"])).json()
    live = next(k for k in listed if k["env"] == "live")
    raw = org["keys"]["live"]
    assert live["hint"] == f"FOID_LIVE_{raw[10:12]}…{raw[-2:]}" and "secret" not in live

    rows = await sql("SELECT * FROM api_keys WHERE org_id=:o", o=org["id"])
    assert not any(raw in str(v) for row in rows for v in row)     # the raw key is nowhere in the database
