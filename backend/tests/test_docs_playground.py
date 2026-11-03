"""The docs site's live Continue with FOID playground (built-in test app + locked exchange endpoint)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import get_settings
from tests import test_oauth_flow
from tests.conftest import make_user
from tests.test_oauth_flow import OA, pkce, setup_app, sign_in

mail = test_oauth_flow.mail   # the email-capturing fixture, shared with the OAuth tests

PG = "/api/v1/docs-playground"
DOCS = "http://localhost:5177"


async def _code(client: httpx.AsyncClient, client_id: str, challenge: str, user: dict[str, Any], box: list[Any],
                origin: str = DOCS) -> str:
    view = (await client.post(f"{OA}/authorize", json={
        "client_id": client_id, "response_mode": "web_message", "origin": origin, "scope": "identity",
        "state": "docs-state-1", "nonce": "docs-n", "code_challenge": challenge, "code_challenge_method": "S256"})).json()
    assert view["test_mode"] is True and view["app"]["name"] == "FOID Docs playground", view
    tokens = await sign_in(client, view["id"], user["email"], box)
    ok = (await client.post(f"{OA}/requests/{view['id']}/approve",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"})).json()
    return ok["payload"]["code"]


async def test_playground_sign_in_end_to_end(client: httpx.AsyncClient, mail: list[Any]) -> None:
    cfg = (await client.get(f"{PG}/config")).json()
    assert cfg["client_id"] == "foid_app_test_docsplayground" and "identity" in cfg["scopes"]
    user = await make_user(client, first="Ngozi", last="Okafor")
    verifier, challenge = pkce()
    code = await _code(client, cfg["client_id"], challenge, user, mail)

    r = await client.post(f"{PG}/exchange", json={"code": code, "code_verifier": verifier})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["object"] == "foid_sign_in" and res["sandbox"] is True and res["nonce"] == "docs-n"
    assert (res["subject"]["first_name"], res["subject"]["last_name"]) == ("Ngozi", "Okafor")
    assert user["nin"] not in r.text and user["email"] not in r.text          # sandbox data only

    again = await client.post(f"{PG}/exchange", json={"code": code, "code_verifier": verifier})
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


async def test_wrong_verifier_refused(client: httpx.AsyncClient, mail: list[Any]) -> None:
    cfg = (await client.get(f"{PG}/config")).json()
    user = await make_user(client)
    _, challenge = pkce()
    code = await _code(client, cfg["client_id"], challenge, user, mail)
    other, _ = pkce()
    r = await client.post(f"{PG}/exchange", json={"code": code, "code_verifier": other})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


async def test_cannot_exchange_a_business_apps_code(client: httpx.AsyncClient, mail: list[Any]) -> None:
    """Codes from any other app are refused, even with the right verifier."""
    app = await setup_app(client)
    user = await make_user(client)
    verifier, challenge = pkce()
    view = (await client.post(f"{OA}/authorize", json={
        "client_id": app["client_id"], "response_mode": "web_message", "origin": "https://shop.example",
        "scope": "identity", "state": "s-1234567", "code_challenge": challenge, "code_challenge_method": "S256"})).json()
    tokens = await sign_in(client, view["id"], user["email"], mail)
    ok = (await client.post(f"{OA}/requests/{view['id']}/approve",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"})).json()
    r = await client.post(f"{PG}/exchange", json={"code": ok["payload"]["code"], "code_verifier": verifier})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


async def test_other_origins_refused(client: httpx.AsyncClient) -> None:
    cfg = (await client.get(f"{PG}/config")).json()
    _, challenge = pkce()
    r = await client.post(f"{OA}/authorize", json={
        "client_id": cfg["client_id"], "response_mode": "web_message", "origin": "https://evil.example",
        "scope": "profile", "state": "s-1234567", "code_challenge": challenge, "code_challenge_method": "S256"})
    assert r.status_code >= 400


async def test_switched_off(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "DOCS_PLAYGROUND", False)
    assert (await client.get(f"{PG}/config")).status_code == 404
    assert (await client.post(f"{PG}/exchange", json={"code": "x", "code_verifier": "v" * 43})).status_code == 404
