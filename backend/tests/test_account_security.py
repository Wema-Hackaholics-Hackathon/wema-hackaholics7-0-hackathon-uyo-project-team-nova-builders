"""FOID user sign-in security: authenticator 2FA, new-device login alerts, FOID code."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from app.core import totp
from app.routers import credentials as credentials_router
from app.services import user_signin
from tests.conftest import make_user, sql

PW = "Passw0rd!x"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    box: list[dict[str, Any]] = []

    async def fake(**kw: Any) -> bool:
        box.append(kw)
        return True
    monkeypatch.setattr(user_signin, "send_email", fake)
    return box


async def _login(client: httpx.AsyncClient, email: str, device: str, ua: str = "Mozilla/5.0 (Windows NT 10.0) Chrome/130") -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": PW, "device_id": device},
                             headers={"User-Agent": ua})


async def test_login_alert_only_for_new_devices(client: httpx.AsyncClient, sent: list[dict[str, Any]]) -> None:
    u = await make_user(client)
    assert (await _login(client, u["email"], "dev-a")).status_code == 200   # first device = baseline
    assert sent == []
    assert (await _login(client, u["email"], "dev-a")).status_code == 200   # same device
    assert sent == []
    assert (await _login(client, u["email"], "dev-b", ua="Mozilla/5.0 (iPhone) Safari/605")).status_code == 200
    assert len(sent) == 1 and sent[0]["to"] == u["email"]
    assert "Safari on iPhone" in sent[0]["html"] and "New sign-in" in sent[0]["subject"]
    notes = (await client.get("/api/v1/notifications", headers=u["headers"])).json()
    assert any(n["message"] == "New sign-in to your account" for n in notes)

    # turned off → no email for another new device
    r = await client.patch("/api/v1/auth/me/security", json={"login_alerts": False}, headers=u["headers"])
    assert r.status_code == 200 and r.json()["login_alerts"] is False
    assert (await _login(client, u["email"], "dev-c")).status_code == 200
    assert len(sent) == 1
    sec = (await client.get("/api/v1/auth/me/security", headers=u["headers"])).json()
    assert len(sec["devices"]) == 3


async def test_two_factor_setup_login_and_disable(client: httpx.AsyncClient, sent: list[dict[str, Any]]) -> None:
    u = await make_user(client)
    setup = (await client.post("/api/v1/auth/me/2fa/setup", headers=u["headers"])).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/FOID:")
    bad = await client.post("/api/v1/auth/me/2fa/enable", json={"code": "000000"}, headers=u["headers"])
    assert bad.status_code == 400
    ok = await client.post("/api/v1/auth/me/2fa/enable", json={"code": totp.code_at(secret)}, headers=u["headers"])
    assert ok.status_code == 200 and ok.json()["two_factor_enabled"] is True
    assert (await client.get("/api/v1/auth/me", headers=u["headers"])).json()["two_factor_enabled"] is True

    r = (await _login(client, u["email"], "dev-a")).json()
    assert r["mfa_required"] is True and "access_token" not in r
    wrong = await client.post("/api/v1/auth/login/2fa", json={"mfa_token": r["mfa_token"], "code": "123456"})
    assert wrong.status_code == 400
    # the code used to enable is refused (replay); the next step's code works
    next_code = totp.code_at(secret, time.time() + 30)
    done = await client.post("/api/v1/auth/login/2fa", json={"mfa_token": r["mfa_token"], "code": next_code})
    assert done.status_code == 200 and done.json()["access_token"]
    # a 2FA ticket is not a session token
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r['mfa_token']}"})).status_code == 401

    nope = await client.post("/api/v1/auth/me/2fa/disable", json={"password": "wrong", "code": "1"}, headers=u["headers"])
    assert nope.status_code == 400
    # every code in the ±30 s window is now used; pretend the clock moved on (real users wait for the next code)
    await sql("UPDATE users SET totp_last_step = :s WHERE id = :u", s=int(time.time() // 30) - 2, u=u["id"])
    off = await client.post("/api/v1/auth/me/2fa/disable",
                            json={"password": PW, "code": totp.code_at(secret)}, headers=u["headers"])
    assert off.status_code == 200 and off.json()["two_factor_enabled"] is False
    assert "access_token" in (await _login(client, u["email"], "dev-a")).json()


async def test_foid_code_shows_only_minimal_public_facts(client: httpx.AsyncClient) -> None:
    u = await make_user(client, first="Wiseman", last="Umanah")
    code = (await client.post("/api/v1/credentials/me/code", headers=u["headers"])).json()
    assert code["code"].startswith("FOID-") and code["url"].endswith(code["token"])
    r = await client.get(f"/api/v1/credentials/code/{code['token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["holder"] == "Wiseman U."
    assert body["checks"]["email"] is True and body["checks"]["nin"] is False
    assert body["checks"]["age_over_18"] is None
    text = r.text
    for secret in (u["email"], u["nin"], u["nin"][-4:], "Umanah", u["id"]):
        assert secret not in text
    assert (await client.get("/api/v1/credentials/code/not-a-token")).status_code == 404


async def test_foid_code_expires(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    u = await make_user(client)
    token = (await client.post("/api/v1/credentials/me/code", headers=u["headers"])).json()["token"]
    monkeypatch.setattr(credentials_router, "CODE_TTL_SECONDS", -1)
    r = await client.get(f"/api/v1/credentials/code/{token}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "code_invalid"
