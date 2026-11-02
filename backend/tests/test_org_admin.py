"""Phase 6: two-step sign-in, Security settings, danger zone, invites, business cap."""

from __future__ import annotations

import base64
import re
import time
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.core import totp
from app.services import console_notify
from tests.conftest import make_member, make_org, sql

AUTH = "/api/v1/console/auth"
BIZ = "/api/v1/business/organisations"


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []

    async def fake(*, to: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append((to, subject, body))

    monkeypatch.setattr(console_notify, "send_email", fake)
    return sent


def test_totp_matches_rfc6238_vector_and_refuses_replay() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59) == "287082"            # RFC 6238 appendix B (last 6 digits)
    now_code = totp.code_at(secret)
    step = totp.verify(secret, now_code)
    assert step is not None and totp.verify(secret, now_code, last_step=step) is None


async def _enable_2fa(client: httpx.AsyncClient, m: dict[str, Any]) -> str:
    secret = (await client.post(f"{AUTH}/me/2fa/setup", headers=m["headers"])).json()["secret"]
    r = await client.post(f"{AUTH}/me/2fa/enable", json={"code": totp.code_at(secret)}, headers=m["headers"])
    assert r.json()["two_factor_enabled"] is True
    await sql("UPDATE console_users SET totp_last_step=NULL WHERE id=:i", i=m["id"])   # let the test reuse "now"
    return secret


async def test_two_step_sign_in(client: httpx.AsyncClient) -> None:
    m = await make_member(client)
    secret = await _enable_2fa(client, m)
    r = (await client.post(f"{AUTH}/login", json={"email": m["email"], "password": "Passw0rd!x"})).json()
    assert r["mfa_required"] is True and r["access_token"] is None
    assert (await client.post(f"{AUTH}/login/2fa", json={"mfa_token": r["mfa_token"], "code": "000000"})).status_code == 400
    ok = await client.post(f"{AUTH}/login/2fa", json={"mfa_token": r["mfa_token"], "code": totp.code_at(secret)})
    assert ok.status_code == 200 and ok.json()["access_token"]
    again = await client.post(f"{AUTH}/login/2fa", json={"mfa_token": r["mfa_token"], "code": totp.code_at(secret)})
    assert again.status_code == 400                                           # same code can't be used twice
    assert (await client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {r['mfa_token']}"})).status_code == 401

    await sql("UPDATE console_users SET totp_last_step=NULL WHERE id=:i", i=m["id"])
    r = await client.post(f"{AUTH}/me/2fa/disable", json={"password": "Passw0rd!x", "code": totp.code_at(secret)}, headers=m["headers"])
    assert r.json()["two_factor_enabled"] is False


async def test_profile_and_password(client: httpx.AsyncClient) -> None:
    m = await make_member(client)
    assert (await client.patch(f"{AUTH}/me", json={"first_name": "Adaeze"}, headers=m["headers"])).json()["first_name"] == "Adaeze"
    bad = await client.post(f"{AUTH}/me/password", json={"current_password": "nope", "new_password": "N3w!passw0rd"}, headers=m["headers"])
    assert bad.status_code == 400
    r = await client.post(f"{AUTH}/me/password", json={"current_password": "Passw0rd!x", "new_password": "N3w!passw0rd"}, headers=m["headers"])
    assert r.status_code == 200 and r.json()["refresh_token"]
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": m["refresh_token"]})).status_code == 401   # old session out


async def test_require_2fa_for_a_business(client: httpx.AsyncClient) -> None:
    owner, dev = await make_member(client), await make_member(client)
    org = await make_org(client, owner)
    await client.post(f"{BIZ}/{org['id']}/members", json={"email": dev["email"], "role": "developer"}, headers=owner["headers"])
    sec = {"require_2fa": True, "alert_on_key_create": True, "ip_allowlist": []}
    r = await client.put(f"{BIZ}/{org['id']}/security", json=sec, headers=owner["headers"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "two_factor_needed_first"
    secret = await _enable_2fa(client, owner)
    assert (await client.put(f"{BIZ}/{org['id']}/security", json=sec, headers=owner["headers"])).status_code == 200

    r = await client.get(f"{BIZ}/{org['id']}/api-keys", headers=dev["headers"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "two_factor_required"
    orgs = (await client.get(BIZ, headers=dev["headers"])).json()
    assert next(o for o in orgs if o["id"] == org["id"])["require_2fa"] is True        # console can explain why
    r = await client.post(f"{AUTH}/me/2fa/disable", json={"password": "Passw0rd!x", "code": totp.code_at(secret)}, headers=owner["headers"])
    assert r.status_code == 409                                                         # can't drop it while required


async def test_ip_allowlist_applies_to_live_keys(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    url = f"{BIZ}/{org['id']}/security"
    bad = await client.put(url, json={"require_2fa": False, "alert_on_key_create": True, "ip_allowlist": ["not-an-ip"]}, headers=owner["headers"])
    assert bad.status_code == 422
    await client.put(url, json={"require_2fa": False, "alert_on_key_create": True, "ip_allowlist": ["10.0.0.0/8"]}, headers=owner["headers"])
    r = await client.get("/api/open/v1/ping", headers=org["h"]["live"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "ip_not_allowed"
    assert (await client.get("/api/open/v1/ping", headers=org["h"]["test"])).status_code == 200      # test keys unaffected
    await client.put(url, json={"require_2fa": False, "alert_on_key_create": True, "ip_allowlist": ["127.0.0.1", "10.0.0.0/8"]}, headers=owner["headers"])
    assert (await client.get("/api/open/v1/ping", headers=org["h"]["live"])).status_code == 200


async def test_key_created_alert(client: httpx.AsyncClient, mail: list[tuple[str, str, str]]) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)                     # creates a test key → alert
    assert mail and mail[-1][0] == owner["email"] and "API key created" in mail[-1][1]
    mail.clear()
    await client.put(f"{BIZ}/{org['id']}/security", json={"require_2fa": False, "alert_on_key_create": False, "ip_allowlist": []},
                     headers=owner["headers"])
    await client.post(f"{BIZ}/{org['id']}/api-keys", json={"env": "test"}, headers=owner["headers"])
    assert mail == []


async def test_danger_zone(client: httpx.AsyncClient) -> None:
    owner, admin = await make_member(client), await make_member(client)
    org = await make_org(client, owner)
    await client.post(f"{BIZ}/{org['id']}/members", json={"email": admin["email"], "role": "admin"}, headers=owner["headers"])
    assert (await client.post(f"{BIZ}/{org['id']}/api-keys/revoke-all", headers=admin["headers"])).status_code == 403   # owner only
    assert (await client.post(f"{BIZ}/{org['id']}/api-keys/revoke-all", headers=owner["headers"])).json() == {"revoked": 1}
    assert (await client.get("/api/open/v1/ping", headers=org["h"]["test"])).status_code == 401

    k = (await client.post(f"{BIZ}/{org['id']}/api-keys", json={"env": "test"}, headers=owner["headers"])).json()["secret"]
    h = {"Authorization": f"Bearer {k}"}
    r = await client.post(f"{BIZ}/{org['id']}/deactivate", json={"confirm_name": "wrong"}, headers=owner["headers"])
    assert r.status_code == 422
    r = await client.post(f"{BIZ}/{org['id']}/deactivate", json={"confirm_name": org["name"]}, headers=owner["headers"])
    assert r.json()["status"] == "suspended"
    assert (await client.get("/api/open/v1/ping", headers=h)).json()["error"]["code"] == "organisation_suspended"
    assert (await client.get(f"{BIZ}/{org['id']}/api-keys", headers=owner["headers"])).status_code == 423
    assert (await client.get(f"{BIZ}/{org['id']}", headers=owner["headers"])).json()["deactivated_at"]
    assert (await client.post(f"{BIZ}/{org['id']}/reactivate", headers=owner["headers"])).json() == {"status": "active"}
    assert (await client.get("/api/open/v1/ping", headers=h)).status_code == 200

    await client.post(f"{BIZ}/{org['id']}/deactivate", json={"confirm_name": org["name"]}, headers=owner["headers"])
    await sql("UPDATE organisations SET deactivated_at=:t WHERE id=:o", t=datetime(2000, 1, 1), o=org["id"])
    from app.config import _get_session_factory
    from app.services.maintenance_service import run_cleanup
    async with _get_session_factory()() as db:
        assert (await run_cleanup(db))["deactivated_organisations"] >= 1
    assert await sql("SELECT 1 FROM organisations WHERE id=:o", o=org["id"]) == []
    assert await sql("SELECT 1 FROM api_keys WHERE org_id=:o", o=org["id"]) == []


def _link_token(mail: list[tuple[str, str, str]]) -> str:
    return re.findall(r"/invite/(inv-[\w-]+)", mail[-1][2])[-1]


async def test_invites(client: httpx.AsyncClient, mail: list[tuple[str, str, str]]) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    url = f"{BIZ}/{org['id']}/invites"
    r = await client.post(url, json={"email": "New.Person@biz.example", "role": "developer"}, headers=owner["headers"])
    assert r.status_code == 201 and r.json()["email"] == "new.person@biz.example"
    token = _link_token(mail)
    assert mail[-1][0] == "new.person@biz.example"

    r = await client.post(url, json={"email": "third@biz.example", "role": "viewer"}, headers=owner["headers"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "seat_limit"          # Starter: 2 seats

    info = (await client.get(f"/api/v1/console/invites/{token}")).json()
    assert info["org_name"] == org["name"] and info["role"] == "developer" and info["has_account"] is False
    r = await client.post(f"/api/v1/console/invites/{token}/accept", json={"first_name": "New", "last_name": "Person", "password": "weak"})
    assert r.status_code == 422
    r = await client.post(f"/api/v1/console/invites/{token}/accept",
                          json={"first_name": "New", "last_name": "Person", "password": "Passw0rd!x"})
    assert r.status_code == 200 and r.json()["access_token"]
    newbie = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{AUTH}/me", headers=newbie)).json()["email_verified"] is True
    assert (await client.get(f"{BIZ}/{org['id']}/api-keys", headers=newbie)).status_code == 200      # developer
    assert (await client.get(f"/api/v1/console/invites/{token}")).status_code == 410                 # used

    # someone who already has an account must sign in as that account
    existing = await make_member(client)
    await client.delete(f"{BIZ}/{org['id']}/members/" + next(
        m["id"] for m in (await client.get(f"{BIZ}/{org['id']}/members", headers=owner["headers"])).json()
        if m["email"] == "new.person@biz.example"), headers=owner["headers"])                       # free a seat
    await client.post(url, json={"email": existing["email"], "role": "viewer"}, headers=owner["headers"])
    first = _link_token(mail)
    await client.post(f"{url}/{(await client.get(url, headers=owner['headers'])).json()[0]['id']}/resend", headers=owner["headers"])
    token = _link_token(mail)
    assert token != first and (await client.get(f"/api/v1/console/invites/{first}")).status_code == 404   # old link dead
    assert (await client.post(f"/api/v1/console/invites/{token}/accept", json={})).status_code == 401
    assert (await client.post(f"/api/v1/console/invites/{token}/accept", json={}, headers=owner["headers"])).status_code == 401
    r = await client.post(f"/api/v1/console/invites/{token}/accept", json={}, headers=existing["headers"])
    assert r.status_code == 200 and "access_token" not in r.json()
    assert (await client.get(f"{BIZ}/{org['id']}", headers=existing["headers"])).json()["role"] == "viewer"


async def test_business_cap_until_approved(client: httpx.AsyncClient) -> None:
    m = await make_member(client)                           # signup already created business #1
    for _ in range(4):
        assert (await client.post(BIZ, json={"name": f"Biz {time.time()}"}, headers=m["headers"])).status_code == 201
    r = await client.post(BIZ, json={"name": "One too many"}, headers=m["headers"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "organisation_limit"
    some = (await client.get(BIZ, headers=m["headers"])).json()[0]
    await sql("UPDATE organisations SET kyb_status='approved' WHERE id=:o", o=some["id"])
    assert (await client.post(BIZ, json={"name": "Now allowed"}, headers=m["headers"])).status_code == 201
