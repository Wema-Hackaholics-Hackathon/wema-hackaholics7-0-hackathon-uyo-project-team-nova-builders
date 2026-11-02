"""Request logs, chart stats, activity feed, search and CSV exports."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import httpx

from tests.conftest import make_member, make_org, sql

OPEN = "/api/open/v1"
BIZ = "/api/v1/business/organisations"
CONSENT = {"obtained": True, "purpose": "Account opening"}


async def test_open_api_calls_are_logged_without_personal_data(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    h = org["h"]["test"]
    r = await client.post(f"{OPEN}/checks/nin?debug=1", headers=h, json={"first_name": "Ada", "last_name": "Obi",
                                                                         "number": "12345678900", "consent": CONSENT})
    req_id = r.headers["FOID-Request-Id"]
    assert req_id.startswith("req_")
    await client.get(f"{OPEN}/subjects/nope", headers=h)                                  # 404
    await client.get(f"{OPEN}/ping", headers={"Authorization": "Bearer FOID_TEST_unknown"})  # unknown key: not attributable

    logs = (await client.get(f"{BIZ}/{org['id']}/request-logs?env=test", headers=owner["headers"])).json()
    assert logs["total"] == 2
    first = logs["data"][-1]
    assert first["request_id"] == req_id and first["method"] == "POST" and first["path"] == "/v1/checks/nin"
    assert first["status"] == 200 and first["key_hint"].startswith("FOID_TEST_") and first["latency_ms"] >= 0
    stored = await sql("SELECT * FROM api_request_logs WHERE org_id=:o", o=org["id"])
    assert not any("12345678900" in str(v) or "Ada" in str(v) or "debug" in str(v) for row in stored for v in row)

    four = (await client.get(f"{BIZ}/{org['id']}/request-logs?env=test&status_class=4", headers=owner["headers"])).json()
    assert [d["status"] for d in four["data"]] == [404]
    by_id = (await client.get(f"{BIZ}/{org['id']}/request-logs", params={"env": "test", "q": req_id[:10]},
                              headers=owner["headers"])).json()
    assert by_id["data"][0]["request_id"] == req_id
    assert (await client.get(f"{BIZ}/{org['id']}/request-logs?env=live", headers=owner["headers"])).json()["total"] == 0

    stats = (await client.get(f"{BIZ}/{org['id']}/request-stats?env=test&days=7", headers=owner["headers"])).json()
    assert stats["total"] == 2 and stats["failed"] == 1 and len(stats["series"]) == 7
    assert stats["series"][-1] == {"day": datetime.now(timezone.utc).date().isoformat(), "successful": 1, "failed": 1}

    found = (await client.get(f"{BIZ}/{org['id']}/search", params={"q": req_id, "env": "test"}, headers=owner["headers"])).json()
    assert [x["request_id"] for x in found["requests"]] == [req_id]

    await sql("UPDATE api_request_logs SET created_at=:t WHERE org_id=:o", t=datetime(2000, 1, 1), o=org["id"])
    from app.config import _get_session_factory
    from app.services.maintenance_service import run_cleanup
    async with _get_session_factory()() as db:
        assert (await run_cleanup(db))["api_request_logs"] >= 2                        # 30-day retention


async def test_activity_feed_and_exports(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    h = org["h"]["test"]
    await client.post(f"{OPEN}/checks/nin", headers=h, json={"first_name": "=HYPERLINK(1)", "last_name": "Obi",
                                                             "number": "12345678900", "consent": CONSENT, "customer_ref": "c-9"})
    await client.post(f"{OPEN}/verifications", headers=h, json={"checks": ["nin"], "purpose": "Wallet"})

    feed = (await client.get(f"{BIZ}/{org['id']}/activity?env=test", headers=owner["headers"])).json()
    titles = [i["title"] for i in feed]
    assert "Verification started" in titles and "API key created" in titles
    assert next(i for i in feed if i["title"] == "API key created")["actor"] == "Tunde Okafor"
    assert all(i["title"] != "API key created" for i in
               (await client.get(f"{BIZ}/{org['id']}/activity?env=live", headers=owner["headers"])).json())   # test key

    r = await client.get(f"{BIZ}/{org['id']}/users/export?env=test", headers=owner["headers"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][0] == "FOID code" and len(rows) == 3
    assert any(cell.startswith("'=HYPERLINK") for row in rows for cell in row)          # no formula injection

    r = await client.get(f"{BIZ}/{org['id']}/request-logs/export?env=test", headers=owner["headers"])
    assert list(csv.reader(io.StringIO(r.text)))[0][0] == "Request ID"

    viewer = await make_member(client)
    await client.post(f"{BIZ}/{org['id']}/members", json={"email": viewer["email"], "role": "viewer"}, headers=owner["headers"])
    assert (await client.get(f"{BIZ}/{org['id']}/users/export?env=test", headers=viewer["headers"])).status_code == 403
