"""'Continue with FOID': popup API + token exchange (PKCE, client auth, replay, sandbox data, re-match, guests)."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwk, jwt

from app.config import _get_session_factory
from app.models import FaceEnrolment, LivenessAttempt
from app.services import oauth_flow, user_signin
from tests.conftest import make_member, make_org, make_user, sql

OA = "/api/v1/oauth"
TOKEN = "/api/open/v1/oauth/token"
ORIGIN = "https://shop.example"


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    box: list[dict[str, Any]] = []

    async def fake(**kw: Any) -> bool:
        box.append(kw)
        return True
    monkeypatch.setattr(oauth_flow, "send_email", fake)
    monkeypatch.setattr(user_signin, "send_email", fake)
    return box


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def setup_app(client: httpx.AsyncClient, *, live: bool = False, scopes: list[str] | None = None) -> dict[str, Any]:
    owner = await make_member(client)
    org = await make_org(client, owner, live=live)
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/apps", headers=owner["headers"], json={
        "env": "live" if live else "test", "name": "Shop web", "origins": [ORIGIN],
        "redirect_uris": [f"{ORIGIN}/cb"], "scopes": scopes or ["identity", "contact", "liveness"]})
    assert r.status_code == 201, r.text
    return {**r.json(), "org": org, "owner": owner}


async def authorize(client: httpx.AsyncClient, app: dict[str, Any], challenge: str, **over: Any) -> httpx.Response:
    body = {"client_id": app["client_id"], "response_mode": "web_message", "origin": ORIGIN,
            "scope": "identity contact", "state": "state-123456", "nonce": "n-1", "code_challenge": challenge,
            "code_challenge_method": "S256", **over}
    return await client.post(f"{OA}/authorize", json=body)


async def sign_in(client: httpx.AsyncClient, rid: str, email: str, mail: list[dict[str, Any]]) -> dict[str, Any]:
    assert (await client.post(f"{OA}/requests/{rid}/email", json={"email": email})).status_code == 200
    code = re.search(r"(\d{6})", mail[-1]["subject"]).group(1)  # type: ignore[union-attr]
    r = await client.post(f"{OA}/requests/{rid}/email/verify", json={"code": code, "device_id": "popup-1"})
    assert r.status_code == 200, r.text
    return r.json()


async def exchange(client: httpx.AsyncClient, app: dict[str, Any], code: str, verifier: str, **over: Any) -> httpx.Response:
    return await client.post(TOKEN, data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                                          "client_id": app["client_id"], "client_secret": app["client_secret"], **over})


async def test_test_mode_sign_in_real_name_sandbox_data_and_replay(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client)
    user = await make_user(client, first="Wiseman", last="Umanah")
    verifier, challenge = pkce()
    view = (await authorize(client, app, challenge)).json()
    assert view["test_mode"] is True and view["app"]["name"] == "Shop web"
    assert [s["scope"] for s in view["scopes"]] == ["contact", "identity", "profile"]
    tokens = await sign_in(client, view["id"], user["email"], mail)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    rv = (await client.get(f"{OA}/requests/{view['id']}/review", headers=h)).json()
    assert rv["missing"] == [] and rv["rematch_required"] is False
    ok = (await client.post(f"{OA}/requests/{view['id']}/approve", headers=h)).json()
    assert ok["origin"] == ORIGIN and ok["payload"]["state"] == "state-123456"
    code = ok["payload"]["code"]

    r = await exchange(client, app, code, verifier)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    res = r.json()
    assert res["sandbox"] is True and res["nonce"] == "n-1" and res["foid_account"] is True
    s = res["subject"]
    assert (s["first_name"], s["last_name"]) == ("Wiseman", "Umanah")                 # real
    assert s["nin"] == {"verified": True, "last4": "0001"} and s["email"] == "sandbox.person@example.com"   # dummy
    assert user["nin"] not in r.text and user["email"] not in r.text
    # shows in the person's Connected apps and the business's request logs
    apps = (await client.get("/api/v1/connected-apps", headers=user["headers"])).json()
    assert apps[0]["status"] == "active" and apps[0]["grants"][0]["source"] == "foid_oauth"
    logs = await sql("SELECT path, status, key_hint FROM api_request_logs WHERE org_id=:o", o=app["org"]["id"])
    assert ("/v1/oauth/token", 200, app["client_id"]) in [tuple(x) for x in logs]

    # the same code again → refused, and what it produced is revoked (it may have leaked)
    again = await exchange(client, app, code, verifier)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
    apps = (await client.get("/api/v1/connected-apps", headers=user["headers"])).json()
    assert apps[0]["status"] == "revoked"


async def test_exchange_rejections(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client)
    user = await make_user(client)
    verifier, challenge = pkce()
    rid = (await authorize(client, app, challenge)).json()["id"]
    tokens = await sign_in(client, rid, user["email"], mail)
    code = (await client.post(f"{OA}/requests/{rid}/approve",
                              headers={"Authorization": f"Bearer {tokens['access_token']}"})).json()["payload"]["code"]
    wrong_secret = await exchange(client, app, code, verifier, client_secret="foid_cs_test_" + "x" * 40)
    assert wrong_secret.status_code == 401 and wrong_secret.json()["error"] == "invalid_client"
    assert (await exchange(client, app, code, verifier, client_secret="")).status_code == 401
    bad_pkce = await exchange(client, app, code, pkce()[0])
    assert bad_pkce.status_code == 400 and "PKCE" in bad_pkce.json()["error_description"]
    assert (await exchange(client, app, code, verifier, grant_type="password")).json()["error"] == "unsupported_grant_type"
    # client_secret_basic works
    basic = base64.b64encode(f"{app['client_id']}:{app['client_secret']}".encode()).decode()
    r = await client.post(TOKEN, data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
                          headers={"Authorization": f"Basic {basic}"})
    assert r.status_code == 200, r.text


async def test_code_expires_after_60s(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client)
    user = await make_user(client)
    verifier, challenge = pkce()
    rid = (await authorize(client, app, challenge)).json()["id"]
    tokens = await sign_in(client, rid, user["email"], mail)
    code = (await client.post(f"{OA}/requests/{rid}/approve",
                              headers={"Authorization": f"Bearer {tokens['access_token']}"})).json()["payload"]["code"]
    await sql("UPDATE oauth_requests SET code_expires_at=:t WHERE id=:i", t=datetime(2020, 1, 1), i=rid)
    assert (await exchange(client, app, code, verifier)).json()["error"] == "invalid_grant"


async def test_authorize_validation(client: httpx.AsyncClient) -> None:
    app = await setup_app(client)
    _, ch = pkce()
    assert (await authorize(client, app, ch, client_id="foid_app_test_nope")).json()["error"]["code"] == "invalid_client"
    assert (await authorize(client, app, ch, origin="https://evil.example")).json()["error"]["code"] == "invalid_origin"
    assert (await authorize(client, app, ch, origin="http://localhost:3000")).status_code == 200   # test: loopback ok
    assert (await authorize(client, app, ch, code_challenge="short")).json()["error"]["code"] == "invalid_request"
    assert (await authorize(client, app, ch, code_challenge_method="plain")).status_code == 400
    assert (await authorize(client, app, ch, state="x")).status_code == 400
    assert (await authorize(client, app, ch, scope="financial")).json()["error"]["code"] == "invalid_scope"
    assert (await authorize(client, app, ch, response_mode="query", redirect_uri=f"{ORIGIN}/other")).status_code == 400
    q = await authorize(client, app, ch, response_mode="query", redirect_uri=f"{ORIGIN}/cb")
    assert q.status_code == 200
    denied = (await client.post(f"{OA}/requests/{q.json()['id']}/deny")).json()
    assert denied["redirect_url"] == f"{ORIGIN}/cb?state=state-123456&error=access_denied"
    live = await setup_app(client, live=True)
    assert (await authorize(client, live, ch, origin="http://localhost:3000")).status_code == 400


async def _enrol_face(user_id: str) -> None:
    async with _get_session_factory()() as db:
        db.add(FaceEnrolment(user_id=user_id, template_enc=b"t", face_png=b"p", face_sha256="s", receipt="r",
                             face_quality=0.9, model="sface_2021dec", consent_at=datetime.now(timezone.utc)))
        await db.commit()


async def _face_check(user_id: str, score: float) -> None:
    async with _get_session_factory()() as db:
        db.add(LivenessAttempt(user_id=user_id, nonce=secrets.token_hex(4), purpose="verify", passed=True, match_score=score))
        await db.commit()


async def test_live_needs_missing_steps_and_fresh_face_rematch(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client, live=True)
    user = await make_user(client)
    verifier, challenge = pkce()
    rid = (await authorize(client, app, challenge, scope="identity contact liveness")).json()["id"]
    h = {"Authorization": f"Bearer {(await sign_in(client, rid, user['email'], mail))['access_token']}"}
    rv = (await client.get(f"{OA}/requests/{rid}/review", headers=h)).json()
    assert rv["missing"] == ["liveness", "nin"] and rv["rematch_required"] is True
    assert (await client.post(f"{OA}/requests/{rid}/approve", headers=h)).json()["error"]["code"] == "steps_missing"

    await _enrol_face(user["id"])
    await sql("UPDATE users SET nin_verified_at=CURRENT_TIMESTAMP, date_of_birth='1991-02-03' WHERE id=:u", u=user["id"])
    await _face_check(user["id"], 0.1)    # a face check that did NOT match doesn't count
    r = await client.post(f"{OA}/requests/{rid}/approve", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "rematch_required"
    await _face_check(user["id"], 0.9)
    code = (await client.post(f"{OA}/requests/{rid}/approve", headers=h)).json()["payload"]["code"]
    res = (await exchange(client, app, code, verifier)).json()
    assert res["sandbox"] is False and res["face_rematched_at"]
    assert res["subject"]["nin"]["last4"] == user["nin"][-4:] and res["subject"]["email"] == user["email"]
    assert res["subject"]["date_of_birth"] == "1991-02-03" and "reverify" in [c["type"] for c in res["checks"]]

    # coming back to the same business: no re-match needed
    _, ch2 = pkce()
    rid2 = (await authorize(client, app, ch2)).json()["id"]
    assert (await client.get(f"{OA}/requests/{rid2}/review", headers=h)).json()["rematch_required"] is False


async def test_private_key_jwt(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client)
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = jwk.construct(priv.public_key(), "ES256").to_dict()
    r = await client.patch(f"/api/v1/business/organisations/{app['org']['id']}/apps/{app['id']}",
                           headers=app["owner"]["headers"], json={"public_jwk": pub, "auth_method": "private_key_jwt"})
    assert r.status_code == 200, r.text
    user = await make_user(client)
    verifier, challenge = pkce()
    rid = (await authorize(client, app, challenge)).json()["id"]
    h = {"Authorization": f"Bearer {(await sign_in(client, rid, user['email'], mail))['access_token']}"}
    code = (await client.post(f"{OA}/requests/{rid}/approve", headers=h)).json()["payload"]["code"]
    assert (await exchange(client, app, code, verifier)).status_code == 401      # secret no longer accepted
    priv_jwk = jwk.construct(priv, "ES256").to_dict()

    def assertion(aud: str, exp: float) -> str:
        return jwt.encode({"iss": app["client_id"], "sub": app["client_id"], "aud": aud, "exp": exp,
                           "jti": secrets.token_hex(8)}, priv_jwk, algorithm="ES256")
    base = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_assertion_type": oauth_flow.ASSERTION_TYPE}
    far = await client.post(TOKEN, data={**base, "client_assertion": assertion(f"http://test{TOKEN}", time.time() + 3600)})
    assert far.status_code == 401
    wrong_aud = await client.post(TOKEN, data={**base, "client_assertion": assertion("https://elsewhere/token", time.time() + 60)})
    assert wrong_aud.status_code == 401
    ok = await client.post(TOKEN, data={**base, "client_assertion": assertion(f"http://test{TOKEN}", time.time() + 60)})
    assert ok.status_code == 200, ok.text


async def test_two_factor_user_still_needs_the_app_code(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client)
    user = await make_user(client)
    await sql("UPDATE users SET totp_enabled_at=CURRENT_TIMESTAMP, totp_secret_enc='x' WHERE id=:u", u=user["id"])
    _, challenge = pkce()
    rid = (await authorize(client, app, challenge)).json()["id"]
    r = await sign_in(client, rid, user["email"], mail)
    assert r["mfa_required"] is True and "access_token" not in r


async def test_new_person_hosted_steps_then_save_to_foid(client: httpx.AsyncClient, mail: list[Any]) -> None:
    app = await setup_app(client, scopes=["identity", "contact"])
    verifier, challenge = pkce()
    rid = (await authorize(client, app, challenge)).json()["id"]
    g = await sign_in(client, rid, "newbie@example.com", mail)
    assert g["account"] is False and g["guest_ticket"]
    t = {"ticket": g["guest_ticket"]}
    assert (await client.post(f"{OA}/requests/{rid}/guest/start", json={"ticket": "forged", "first_name": "A", "last_name": "B"})).status_code == 401
    hosted = (await client.post(f"{OA}/requests/{rid}/guest/start",
                                json={**t, "first_name": "Ngozi", "last_name": "Eze", "date_of_birth": "1995-04-12"})).json()["hosted_url"]
    hs = "/api/v1/hosted/sessions/" + hosted.rsplit("/", 1)[1]
    assert (await client.get(hs)).json()["steps"][0]["type"] == "nin"
    assert (await client.post(f"{hs}/consent", json={"accept": True})).status_code == 200
    assert (await client.post(f"{hs}/nin", json={"number": "12345678900"})).json()["status"] == "passed"
    done = (await client.post(f"{hs}/finish")).json()
    assert done["redirect_url"].startswith(f"http://localhost:5173/oauth/continue/{rid}")
    st = (await client.post(f"{OA}/requests/{rid}/guest/status", json=t)).json()
    assert st["can_save_to_foid"] is True and st["first_name"] == "Ngozi"
    saved = (await client.post(f"{OA}/requests/{rid}/guest/save", json=t)).json()
    me = (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {saved['access_token']}"})).json()
    assert me["email"] == "newbie@example.com" and me["email_verified"] is True and me["nin_verified_at"]
    assert (await client.post(f"{OA}/requests/{rid}/guest/save", json=t)).status_code == 409   # only once
    code = (await client.post(f"{OA}/requests/{rid}/guest/finish", json=t)).json()["payload"]["code"]
    res = (await exchange(client, app, code, verifier)).json()
    assert res["foid_account"] is True and res["subject"]["first_name"] == "Ngozi"
    assert res["subject"]["consent"]["status"] == "active"
