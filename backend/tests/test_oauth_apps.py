"""Console 'Continue with FOID' apps: create, URL rules, secrets (once, hashed, rotation overlap), keys, roles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jose import jwk

from app.core.crypto import sha256_hex
from tests.conftest import make_member, make_org, sql


def _base(org: dict) -> str:  # type: ignore[type-arg]
    return f"/api/v1/business/organisations/{org['id']}/apps"


async def test_create_app_shows_secret_once_and_stores_hash(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    r = await client.post(_base(org), headers=owner["headers"], json={
        "env": "test", "name": "Acme web", "origins": ["https://app.acme.com/", "http://localhost:3000"],
        "redirect_uris": ["https://app.acme.com/auth/foid", "http://127.0.0.1:5173/cb"], "scopes": ["identity"]})
    assert r.status_code == 201, r.text
    app = r.json()
    raw = app["client_secret"]
    assert raw.startswith("foid_cs_test_") and app["client_id"].startswith("foid_app_test_")
    assert app["origins"] == ["https://app.acme.com", "http://localhost:3000"]
    assert app["scopes"] == ["profile", "identity"] and app["loopback_allowed"] is True
    assert app["secrets"][0]["hint"].endswith(raw[-2:]) and raw not in str(app["secrets"])
    rows = await sql("SELECT secret_hash FROM oauth_client_secrets")
    assert sha256_hex(raw) in [r[0] for r in rows] and raw not in str(rows)
    listed = (await client.get(_base(org) + "?env=test", headers=owner["headers"])).json()
    assert [a["id"] for a in listed] == [app["id"]] and "client_secret" not in listed[0]


async def test_url_rules(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    bad = [
        ("test", {"origins": ["http://acme.com"]}),                 # http outside loopback
        ("test", {"origins": ["https://acme.com/login"]}),          # origin with a path
        ("test", {"redirect_uris": ["https://acme.com/cb#x"]}),     # fragment
        ("live", {"origins": ["http://localhost:3000"]}),           # localhost in live
        ("live", {"redirect_uris": ["http://127.0.0.1/cb"]}),
        ("live", {}),                                               # live needs somewhere to return to
        ("test", {"scopes": ["everything"]}),
    ]
    for env, extra in bad:
        r = await client.post(_base(org), headers=owner["headers"], json={"env": env, "name": "X app", **extra})
        assert r.status_code == 422, (env, extra, r.text)
    ok = await client.post(_base(org), headers=owner["headers"],
                           json={"env": "live", "name": "Live web", "origins": ["https://acme.com"]})
    assert ok.status_code == 201 and ok.json()["loopback_allowed"] is False


async def test_live_app_needs_kyb(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    r = await client.post(_base(org), headers=owner["headers"],
                          json={"env": "live", "name": "Live", "origins": ["https://acme.com"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "live_mode_disabled"


async def test_rotation_keeps_old_secret_24h_and_revoke(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    app = (await client.post(_base(org), headers=owner["headers"], json={"env": "test", "name": "Web"})).json()
    rot = await client.post(f"{_base(org)}/{app['id']}/secrets", headers=owner["headers"])
    assert rot.status_code == 201
    secrets_ = rot.json()["secrets"]
    assert len(secrets_) == 2
    old = next(s for s in secrets_ if s["expires_at"])
    left = datetime.fromisoformat(old["expires_at"]) - datetime.now(timezone.utc)
    assert timedelta(hours=23) < left <= timedelta(hours=24)
    # once the overlap has passed the old one disappears
    await sql("UPDATE oauth_client_secrets SET expires_at=:t WHERE id=:i",
              t=(datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None), i=old["id"])  # columns hold naive UTC
    assert len((await client.get(_base(org), headers=owner["headers"])).json()[0]["secrets"]) == 1
    new_id = next(s["id"] for s in secrets_ if not s["expires_at"])
    assert (await client.delete(f"{_base(org)}/{app['id']}/secrets/{new_id}", headers=owner["headers"])).status_code == 204
    assert (await client.get(_base(org), headers=owner["headers"])).json()[0]["secrets"] == []


async def test_private_key_jwt_accepts_public_keys_only(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    app = (await client.post(_base(org), headers=owner["headers"], json={"env": "test", "name": "Bank"})).json()
    url = f"{_base(org)}/{app['id']}"
    need_key = await client.patch(url, headers=owner["headers"], json={"auth_method": "private_key_jwt"})
    assert need_key.status_code == 422
    priv = ec.generate_private_key(ec.SECP256R1())
    private_jwk = jwk.construct(priv, "ES256").to_dict()
    leak = await client.patch(url, headers=owner["headers"], json={"public_jwk": private_jwk})
    assert leak.status_code == 422 and "PRIVATE" in leak.json()["error"]["message"]
    public_jwk = jwk.construct(priv.public_key(), "ES256").to_dict()
    r = await client.patch(url, headers=owner["headers"], json={"public_jwk": {**public_jwk, "kid": "k1"}, "auth_method": "private_key_jwt"})
    assert r.status_code == 200, r.text
    assert r.json()["auth_method"] == "private_key_jwt" and r.json()["public_jwk"]["alg"] == "ES256"
    small = rsa.generate_private_key(public_exponent=65537, key_size=1024).public_key()
    weak = await client.patch(url, headers=owner["headers"], json={"public_jwk": jwk.construct(small, "RS256").to_dict()})
    assert weak.status_code == 422


async def test_roles_and_delete(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    viewer = await make_member(client)
    await sql("INSERT INTO org_members (id, org_id, console_user_id, role, created_at) VALUES (:i, :o, :u, 'viewer', CURRENT_TIMESTAMP)",
              i=f"m-{viewer['id']}", o=org["id"], u=viewer["id"])
    assert (await client.get(_base(org), headers=viewer["headers"])).status_code == 403
    app = (await client.post(_base(org), headers=owner["headers"], json={"env": "test", "name": "Web"})).json()
    assert (await client.delete(f"{_base(org)}/{app['id']}", headers=owner["headers"])).status_code == 204
    assert (await client.get(_base(org), headers=owner["headers"])).json() == []
    assert (await client.patch(f"{_base(org)}/{app['id']}", headers=owner["headers"], json={"name": "Again"})).status_code == 404
