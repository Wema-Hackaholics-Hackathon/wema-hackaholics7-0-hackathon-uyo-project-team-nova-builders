"""Console data endpoints: keys per env + rotate, webhook health, Users table, Overview."""

from __future__ import annotations

from typing import Any

from datetime import datetime

import httpx

from tests.conftest import WebhookSink, make_member, make_org, sql

OPEN = "/api/open/v1"
BIZ = "/api/v1/business/organisations"
CONSENT = {"obtained": True, "purpose": "Account opening"}


async def test_keys_by_env_and_rotate(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    h = owner["headers"]
    test_keys = (await client.get(f"{BIZ}/{org['id']}/api-keys?env=test", headers=h)).json()
    assert [k["env"] for k in test_keys] == ["test"]

    r = await client.post(f"{BIZ}/{org['id']}/api-keys/{test_keys[0]['id']}/rotate", headers=h)
    assert r.status_code == 201 and r.json()["secret"].startswith("FOID_TEST_") and r.json()["name"] == test_keys[0]["name"]
    assert (await client.get(f"{OPEN}/ping", headers=org["h"]["test"])).status_code == 401          # old key dead
    new_h = {"Authorization": f"Bearer {r.json()['secret']}"}
    assert (await client.get(f"{OPEN}/ping", headers=new_h)).status_code == 200

    active = (await client.get(f"{BIZ}/{org['id']}/api-keys?env=test", headers=h)).json()
    assert [k["id"] for k in active] == [r.json()["id"]]                                           # revoked hidden
    every = (await client.get(f"{BIZ}/{org['id']}/api-keys?env=test&include_revoked=true", headers=h)).json()
    assert len(every) == 2


async def test_webhooks_by_env_with_last_delivery(client: httpx.AsyncClient, webhook_sink: WebhookSink) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    h = owner["headers"]
    for env in ("test", "live"):
        await client.post(f"{BIZ}/{org['id']}/webhooks", json={"env": env, "url": f"https://{env}.example.com/h"}, headers=h)
    hooks = (await client.get(f"{BIZ}/{org['id']}/webhooks?env=test", headers=h)).json()
    assert [w["url"] for w in hooks] == ["https://test.example.com/h"] and hooks[0]["last_delivery_status"] is None
    await client.post(f"{BIZ}/{org['id']}/webhooks/{hooks[0]['id']}/test", headers=h)
    hooks = (await client.get(f"{BIZ}/{org['id']}/webhooks?env=test", headers=h)).json()
    assert hooks[0]["last_delivery_status"] == "delivered" and hooks[0]["last_delivery_at"]


async def _people(client: httpx.AsyncClient, org: dict[str, Any]) -> dict[str, str]:
    """verified (passed NIN), declined (failed NIN), pending (open hosted flow), revoked."""
    h = org["h"]["test"]
    base = {"last_name": "Obi", "consent": CONSENT}
    ids: dict[str, str] = {}
    r = await client.post(f"{OPEN}/checks/nin", json={**base, "first_name": "Ada", "number": "12345678900",
                                                      "customer_ref": "cust-ok"}, headers=h)
    ids["verified"] = r.json()["subject_id"]
    r = await client.post(f"{OPEN}/checks/nin", json={**base, "first_name": "Ada", "number": "12345678908"}, headers=h)
    ids["declined"] = r.json()["subject_id"]
    r = await client.post(f"{OPEN}/verifications", json={"checks": ["nin"], "purpose": "Wallet", "first_name": "Bola",
                                                          "last_name": "Eze"}, headers=h)
    ids["pending"] = r.json()["subject_id"]
    r = await client.post(f"{OPEN}/checks/bvn", json={**base, "first_name": "Kemi", "number": "22345678900"}, headers=h)
    ids["revoked"] = r.json()["subject_id"]
    await sql("UPDATE consent_grants SET status='revoked' WHERE subject_id=:s", s=ids["revoked"])
    return ids


async def test_users_table_status_search_and_env(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    ids = await _people(client, org)
    h, url = owner["headers"], f"{BIZ}/{org['id']}/users"

    body = (await client.get(f"{url}?env=test", headers=h)).json()
    assert body["counts"] == {"all": 4, "verified": 1, "pending": 1, "declined": 1, "revoked": 1}
    by_id = {u["id"]: u for u in body["data"]}
    assert {sid: by_id[sid]["status"] for sid in ids.values()} == {v: k for k, v in ids.items()}

    revoked = by_id[ids["revoked"]]
    assert revoked["name"] is None and revoked["email"] is None                      # consent gone → no PII
    ok = by_id[ids["verified"]]
    assert ok["name"] == "Ada Obi" and ok["checks"] == ["NIN"] and ok["verified_at"]
    assert ok["code"].startswith("FOID-") and len(ok["code"]) == 14

    one = (await client.get(f"{url}?env=test&status=declined", headers=h)).json()
    assert [u["id"] for u in one["data"]] == [ids["declined"]] and one["total"] == 1 and one["counts"]["all"] == 4
    for q in ("cust-ok", "ada obi", ok["code"], ok["code"].lower()):
        found = (await client.get(f"{url}?env=test", params={"q": q}, headers=h)).json()["data"]
        assert ids["verified"] in [u["id"] for u in found], q
    assert (await client.get(f"{url}?env=test", params={"q": "kemi"}, headers=h)).json()["total"] == 0   # hidden PII isn't searchable

    page = (await client.get(f"{url}?env=test&limit=2&offset=2", headers=h)).json()
    assert len(page["data"]) == 2 and page["total"] == 4
    assert (await client.get(f"{url}?env=live", headers=h)).json()["counts"]["all"] == 0              # test ≠ live


async def test_overview_numbers(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    await _people(client, org)
    ov = (await client.get(f"{BIZ}/{org['id']}/overview?env=test", headers=owner["headers"])).json()
    assert ov["verifications_30d"] == 1 and ov["funnel"]["started"] == 1 and ov["stuck"] == 0
    await sql("UPDATE verifications SET created_at=:t WHERE org_id=:o", t=datetime(2000, 1, 1), o=org["id"])
    ov = (await client.get(f"{BIZ}/{org['id']}/overview?env=test", headers=owner["headers"])).json()
    assert ov["users"]["all"] == 4 and ov["users"]["verified"] == 1
    assert ov["verifications_30d"] == 0 and ov["funnel"] == {"started": 0, "identity_confirmed": 0, "fully_verified": 0}
    assert ov["checks_run"]["nin"] == 2
