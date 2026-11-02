"""Notification bells: the business console's (per member, by role) and the user app's."""

from __future__ import annotations

import httpx

from tests.conftest import make_member, make_org, make_user, sql

BIZ = "/api/v1/business/organisations"


async def _bell(client: httpx.AsyncClient, m: dict, org_id: str) -> dict:  # type: ignore[type-arg]
    return (await client.get(f"{BIZ}/{org_id}/notifications", headers=m["headers"])).json()


async def _team(client: httpx.AsyncClient) -> tuple[dict, dict, dict, dict]:  # type: ignore[type-arg]
    owner, admin, dev = await make_member(client), await make_member(client), await make_member(client)
    org = await make_org(client, owner)
    await sql("UPDATE organisations SET plan_code='business' WHERE id=:o", o=org["id"])   # enough seats
    for m, role in ((admin, "admin"), (dev, "developer")):
        await client.post(f"{BIZ}/{org['id']}/members", json={"email": m["email"], "role": role}, headers=owner["headers"])
    return org, owner, admin, dev


async def test_console_bell_by_role_and_read_state(client: httpx.AsyncClient) -> None:
    org, owner, admin, dev = await _team(client)
    await client.post(f"{BIZ}/{org['id']}/api-keys", json={"env": "test", "name": "Staging"}, headers=owner["headers"])

    a = await _bell(client, admin, org["id"])
    assert a["unread"] == 1 and a["data"][0]["title"] == "New test API key: Staging" and a["data"][0]["link"] == "/api-keys"
    assert (await _bell(client, owner, org["id"]))["unread"] == 0      # you did it — no ping for yourself
    assert (await _bell(client, dev, org["id"]))["unread"] == 0        # key alerts are for owners/admins

    nid = a["data"][0]["id"]
    assert (await client.post(f"{BIZ}/{org['id']}/notifications/{nid}/read", headers=dev["headers"])).status_code == 404   # not yours
    assert (await client.post(f"{BIZ}/{org['id']}/notifications/{nid}/read", headers=admin["headers"])).status_code == 204
    a = await _bell(client, admin, org["id"])
    assert a["unread"] == 0 and a["data"][0]["read"] is True

    await client.post(f"{BIZ}/{org['id']}/api-keys/revoke-all", headers=owner["headers"])
    assert (await _bell(client, dev, org["id"]))["data"][0]["title"] == "All API keys were revoked"
    await client.post(f"{BIZ}/{org['id']}/notifications/read-all", headers=dev["headers"])
    assert (await _bell(client, dev, org["id"]))["unread"] == 0

    await client.post(f"{BIZ}/{org['id']}/deactivate", json={"confirm_name": org["name"]}, headers=owner["headers"])
    b = await _bell(client, dev, org["id"])                            # still readable while deactivated
    assert b["data"][0]["title"] == f"{org['name']} was deactivated"


async def test_go_live_decision_and_consent_revocation_reach_the_bell(client: httpx.AsyncClient) -> None:
    org, owner, admin, dev = await _team(client)
    await sql("UPDATE organisations SET kyb_status='pending' WHERE id=:o", o=org["id"])
    staff = await make_user(client)
    await sql("UPDATE users SET is_admin=TRUE WHERE id=:u", u=staff["id"])
    await client.post(f"/api/v1/admin/organisations/{org['id']}/kyb", json={"approve": False, "note": "CAC report too old"},
                      headers=staff["headers"])
    o = (await _bell(client, owner, org["id"]))["data"][0]
    assert o["title"] == "Go-live review: changes needed" and o["body"] == "CAC report too old" and o["link"] == "/go-live"
    assert (await _bell(client, dev, org["id"]))["unread"] == 0

    # a person revokes consent → reviewers and up hear about it
    from app.config import _get_session_factory
    from app.models import Subject
    from app.services import consent_service
    r = await client.post("/api/open/v1/checks/nin", headers=org["h"]["test"], json={
        "first_name": "Ada", "last_name": "Obi", "number": "12345678900", "consent": {"obtained": True, "purpose": "KYC"}})
    async with _get_session_factory()() as db:
        subject = await db.get(Subject, r.json()["subject_id"])
        assert subject is not None
        await consent_service.revoke_subject(db, org_id=org["id"], subject=subject, by="user", actor_id=None)
        await db.commit()
    d = (await _bell(client, dev, org["id"]))["data"][0]
    assert d["title"].endswith("revoked consent") and d["link"].startswith("/users?q=FOID-")


async def test_user_app_notifications_limit(client: httpx.AsyncClient) -> None:
    user = await make_user(client)
    for i in range(3):
        await sql("INSERT INTO notifications (id, user_id, message, change, reason, action, timestamp, read) "
                  "VALUES (:i, :u, 'm', 'c', 'r', 'a', CURRENT_TIMESTAMP, FALSE)", i=f"n{i}-{user['id']}", u=user["id"])
    assert len((await client.get("/api/v1/notifications?limit=2", headers=user["headers"])).json()) == 2
    assert len((await client.get("/api/v1/notifications", headers=user["headers"])).json()) >= 3


async def test_failing_webhook_pings_developers_once(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import _get_session_factory
    from app.models import WebhookDelivery
    from app.services import webhook_service as wh

    org, owner, admin, dev = await _team(client)
    hook = (await client.post(f"{BIZ}/{org['id']}/webhooks", json={"env": "test", "url": "https://down.example.com/h"},
                              headers=owner["headers"])).json()

    async def down(*_a, **_k):  # type: ignore[no-untyped-def]
        return 500, "Internal Server Error"
    monkeypatch.setattr(wh, "_send", down)
    async with _get_session_factory()() as db:
        for _ in range(2):      # two deliveries give up — still one unread alert
            d = WebhookDelivery(org_id=org["id"], endpoint_id=hook["id"], event_id="evt_x", event_type="user.verified",
                                payload={}, attempts=len(wh._BACKOFF_SECS) - 1)  # pyright: ignore[reportPrivateUsage]
            db.add(d)
            async with wh.new_client() as c:
                await wh.attempt(db, d, c)
            await db.commit()
            assert d.status == "failed"
    bell = await _bell(client, dev, org["id"])
    failing = [n for n in bell["data"] if n["title"] == "Webhook endpoint is failing"]
    assert len(failing) == 1 and "down.example.com" in failing[0]["body"]
