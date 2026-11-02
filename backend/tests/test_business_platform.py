"""Business platform: keys, checks, hosted flow, webhooks, consent revocation, linking."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import httpx
import pytest

from app.core.crypto import decrypt_str
from tests.conftest import (
    FACE_PNG,
    WebhookSink,
    deliver_webhooks,
    finish_liveness,
    make_member,
    make_org,
    make_user,
    sql,
)

OPEN = "/api/open/v1"
CONSENT = {"obtained": True, "purpose": "Account opening"}


async def _webhook(client: httpx.AsyncClient, owner: dict[str, Any], org: dict[str, Any], env: str = "test") -> str:
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/webhooks",
                          json={"env": env, "url": "https://hooks.example.com/foid"}, headers=owner["headers"])
    assert r.status_code == 201, r.text
    return r.json()["secret"]


def _verify_signature(secret: str, request: httpx.Request) -> bool:
    parts = dict(p.split("=", 1) for p in request.headers["FOID-Signature"].split(","))
    expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + request.content, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])


async def _hosted(client: httpx.AsyncClient, org: dict[str, Any], checks: list[str], env: str = "test",
                  **person: Any) -> dict[str, Any]:
    body = {"checks": checks, "purpose": "Open a wallet", "customer_ref": person.pop("customer_ref", None),
            "first_name": "Ada", "last_name": "Obi", **person}
    r = await client.post(f"{OPEN}/verifications", json=body, headers=org["h"][env])
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Keys & auth
# ---------------------------------------------------------------------------

async def test_api_keys_and_live_mode_gate(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)

    r = await client.get(f"{OPEN}/ping", headers=org["h"]["test"])
    assert r.status_code == 200 and r.json()["env"] == "test"

    r = await client.post(f"/api/v1/business/organisations/{org['id']}/api-keys", json={"env": "live"},
                          headers=owner["headers"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "live_mode_disabled"

    r = await client.get(f"{OPEN}/ping", headers={"Authorization": "Bearer sk_test_nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"

    keys = (await client.get(f"/api/v1/business/organisations/{org['id']}/api-keys", headers=owner["headers"])).json()
    assert "secret" not in keys[0] and re.fullmatch(r"FOID_TEST_[A-Za-z0-9]{2}…[A-Za-z0-9]{2}", keys[0]["hint"])
    await client.delete(f"/api/v1/business/organisations/{org['id']}/api-keys/{keys[0]['id']}", headers=owner["headers"])
    r = await client.get(f"{OPEN}/ping", headers=org["h"]["test"])
    assert r.status_code == 401


async def test_roles_enforced(client: httpx.AsyncClient) -> None:
    owner, viewer = await make_member(client), await make_member(client)
    org = await make_org(client, owner)
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/members",
                          json={"email": viewer["email"], "role": "viewer"}, headers=owner["headers"])
    assert r.status_code == 201
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/api-keys", json={"env": "test"},
                          headers=viewer["headers"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "insufficient_role"
    outsider = await make_member(client)
    r = await client.get(f"/api/v1/business/organisations/{org['id']}", headers=outsider["headers"])
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Server-to-server checks
# ---------------------------------------------------------------------------

async def test_direct_nin_and_bvn_checks(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    h = org["h"]["test"]
    base = {"first_name": "Ada", "last_name": "Obi", "consent": CONSENT}

    r = await client.post(f"{OPEN}/checks/nin", json={**base, "number": "12345678900", "customer_ref": "c1"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "passed", r.text
    assert r.json()["data"]["nin_last4"] == "8900" and "12345678900" not in r.text

    r = await client.post(f"{OPEN}/checks/nin", json={**base, "number": "12345678908"}, headers=h)
    assert r.json()["status"] == "failed" and r.json()["reasons"] == ["name_mismatch"]

    r = await client.post(f"{OPEN}/checks/bvn", json={**base, "number": "22345678909"}, headers=h)
    assert r.json()["status"] == "failed" and r.json()["reasons"] == ["not_found"]

    r = await client.post(f"{OPEN}/checks/nin", json={**base, "number": "123"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_nin"

    r = await client.post(f"{OPEN}/checks/nin", json={"number": "12345678900", "first_name": "A", "last_name": "B"},
                          headers=h)
    assert r.status_code == 422   # consent attestation is required


async def test_idempotency(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    h = {**org["h"]["test"], "Idempotency-Key": "abc-1"}
    body = {"number": "12345678900", "first_name": "Ada", "last_name": "Obi", "consent": CONSENT}
    r1 = await client.post(f"{OPEN}/checks/nin", json=body, headers=h)
    r2 = await client.post(f"{OPEN}/checks/nin", json=body, headers=h)
    assert r1.json()["id"] == r2.json()["id"] and r2.headers.get("idempotent-replayed") == "true"
    r3 = await client.post(f"{OPEN}/checks/nin", json={**body, "first_name": "Bola"}, headers=h)
    assert r3.status_code == 409
    stored = await sql("SELECT response FROM idempotency_records")
    assert all("12345678900" not in str(row[0]) for row in stored)


async def test_nin_document_without_ocr_is_an_error_not_a_failure(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    r = await client.post(f"{OPEN}/checks/nin-document", headers=org["h"]["test"],
                          files={"file": ("slip.png", FACE_PNG, "image/png")},
                          data={"consent_obtained": "true", "purpose": "KYC", "first_name": "Ada", "last_name": "Obi"})
    assert r.status_code == 200 and r.json()["status"] == "error" and r.json()["reasons"] == ["ocr_unavailable"]


async def test_nin_document_ocr_extracts_number(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import groq_service

    async def fake_ocr(_b: bytes, _m: str) -> dict[str, Any]:
        return {"document_type": "improved_nin_slip", "nin": "1234 567 8900", "first_name": "Ada",
                "middle_name": None, "last_name": "Obi", "confidence": 0.95}
    monkeypatch.setattr(groq_service, "extract_nin_document", fake_ocr)
    owner = await make_member(client)
    org = await make_org(client, owner)
    r = await client.post(f"{OPEN}/checks/nin-document", headers=org["h"]["test"],
                          files={"file": ("slip.png", FACE_PNG, "image/png")},
                          data={"consent_obtained": "true", "purpose": "KYC"})
    body = r.json()
    assert body["status"] == "passed", body
    assert body["data"]["method"] == "document" and body["data"]["nin_last4"] == "8900"
    assert body["data"]["document_type"] == "improved_nin_slip"


# ---------------------------------------------------------------------------
# Hosted flow (the branded liveness/verification page) + webhooks
# ---------------------------------------------------------------------------

async def test_hosted_flow_end_to_end(client: httpx.AsyncClient, stub_face_verify: None,
                                      webhook_sink: WebhookSink) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    secret = await _webhook(client, owner, org)
    v = await _hosted(client, org, ["nin", "liveness"], customer_ref="cust-42", return_url="https://app.example/done")
    assert v["hosted_url"].endswith(v["client_token"]) and v["status"] == "pending"
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"

    # the link can be fetched again while the verification is open
    again = (await client.get(f"{OPEN}/verifications/{v['id']}", headers=org["h"]["test"])).json()
    assert again["hosted_url"] == v["hosted_url"] and again["client_token"] == v["client_token"]
    raw = await sql("SELECT session_token_enc FROM verifications WHERE id=:i", i=v["id"])
    assert v["client_token"] not in raw[0][0]   # stored encrypted

    s = (await client.get(hs)).json()
    assert s["business"]["name"] == org["name"] and [x["type"] for x in s["steps"]] == ["nin", "liveness"]

    r = await client.post(f"{hs}/nin", json={"number": "12345678900"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "consent_required"

    assert (await client.post(f"{hs}/consent", json={"accept": True})).json()["consent_given"]
    r = await client.post(f"{hs}/nin", json={"number": "12345678900"})
    assert r.json() == {"type": "nin", "status": "passed", "reasons": []}   # no registry data shown to the person

    start = (await client.post(f"{hs}/liveness/start")).json()
    assert len(start["challenges"]) == 3
    finish_liveness(start["session_id"])
    r = await client.post(f"{hs}/liveness/{start['session_id']}/complete")
    assert r.json()["passed"] is True, r.text

    done = (await client.post(f"{hs}/finish")).json()
    assert done["status"] == "completed" and done["outcome"] == "passed"
    assert done["redirect_url"].startswith("https://app.example/done?verification_id=")

    got = (await client.get(f"{OPEN}/verifications/{v['id']}", headers=org["h"]["test"])).json()
    assert got["results"]["nin"]["status"] == "passed" and got["results"]["liveness"]["status"] == "passed"
    assert got["hosted_url"] is None and got["client_token"] is None   # closed → link no longer offered

    assert await deliver_webhooks() >= 1
    events = webhook_sink.events()
    assert [e["type"] for e in events] == ["verification.completed"]
    assert events[0]["data"]["outcome"] == "passed" and events[0]["data"]["customer_ref"] == "cust-42"
    assert _verify_signature(secret, webhook_sink.requests[0])

    r = await client.post(f"{hs}/nin", json={"number": "12345678900"})
    assert r.status_code == 410


async def test_hosted_declined_consent(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    v = await _hosted(client, org, ["bvn"])
    r = await client.post(f"/api/v1/hosted/sessions/{v['client_token']}/consent", json={"accept": False})
    assert r.json()["status"] == "cancelled"
    got = (await client.get(f"{OPEN}/verifications/{v['id']}", headers=org["h"]["test"])).json()
    assert got["consent"]["status"] == "none" and got["status"] == "cancelled"


async def test_attempt_limit(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    v = await _hosted(client, org, ["bvn"])
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"
    await client.post(f"{hs}/consent", json={"accept": True})
    for _ in range(3):
        assert (await client.post(f"{hs}/bvn", json={"number": "22345678909"})).json()["status"] == "failed"
    r = await client.post(f"{hs}/bvn", json={"number": "22345678900"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"


async def test_reverify_matches_stored_face(client: httpx.AsyncClient, stub_face_verify: None) -> None:
    import cv2
    import numpy as np

    owner = await make_member(client)
    org = await make_org(client, owner)
    v = await _hosted(client, org, ["liveness"], customer_ref="rv-1")
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"
    await client.post(f"{hs}/consent", json={"accept": True})
    sid = (await client.post(f"{hs}/liveness/start")).json()["session_id"]
    finish_liveness(sid)
    await client.post(f"{hs}/liveness/{sid}/complete")
    await client.post(f"{hs}/finish")

    async def reverify(png: bytes) -> dict[str, Any]:
        rv = await _hosted(client, org, ["reverify"], subject_id=v["subject_id"])
        h2 = f"/api/v1/hosted/sessions/{rv['client_token']}"
        await client.post(f"{h2}/consent", json={"accept": True})
        sid2 = (await client.post(f"{h2}/liveness/start")).json()["session_id"]
        finish_liveness(sid2, png)
        return (await client.post(f"{h2}/liveness/{sid2}/complete")).json()

    assert (await reverify(FACE_PNG))["passed"] is True
    other = cv2.imencode(".png", np.full((112, 112, 3), 90, np.uint8))[1].tobytes()
    res = await reverify(other)
    assert res["passed"] is False and res["reasons"] == ["face_mismatch"]

    nobody = await _hosted(client, org, ["nin"], customer_ref="no-face")
    r = await client.post(f"{OPEN}/verifications", headers=org["h"]["test"],
                          json={"checks": ["reverify"], "purpose": "Step-up", "subject_id": nobody["subject_id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_face_on_file"


# ---------------------------------------------------------------------------
# Revocation: the person withdraws consent → the business stops getting data
# ---------------------------------------------------------------------------

async def test_user_revocation_stops_all_data(client: httpx.AsyncClient, stub_face_verify: None,
                                              webhook_sink: WebhookSink) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    await _webhook(client, owner, org)
    person = await make_user(client)

    # Person verifies with the business through the hosted page and shares their FOID identity.
    v = await _hosted(client, org, ["nin"], customer_ref="p-1")
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"
    await client.post(f"{hs}/consent", json={"accept": True})
    r = await client.post(f"{hs}/share-foid", headers=person["headers"])
    assert r.status_code == 200, r.text
    await client.post(f"{hs}/nin", json={"number": "12345678900"})
    await client.post(f"{hs}/finish")                       # queues verification.completed (not yet sent)

    apps = (await client.get("/api/v1/connected-apps", headers=person["headers"])).json()
    assert len(apps) == 1 and apps[0]["status"] == "active" and apps[0]["sandbox"] is True

    r = await client.delete(f"/api/v1/connected-apps/{org['id']}", headers=person["headers"])
    assert r.json()["status"] == "revoked"

    # 1. data endpoints refuse
    r = await client.get(f"{OPEN}/subjects/{v['subject_id']}", headers=org["h"]["test"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_revoked"
    r = await client.get(f"{OPEN}/subjects/{v['subject_id']}/checks", headers=org["h"]["test"])
    assert r.status_code == 403
    # 2. verification results are redacted (status only)
    got = (await client.get(f"{OPEN}/verifications/{v['id']}", headers=org["h"]["test"])).json()
    assert got["consent"]["status"] == "revoked" and got["results"]["nin"] == {"status": "passed", "redacted": True}
    # 3. the queued data webhook is cancelled; only consent.revoked goes out
    await deliver_webhooks()
    assert [e["type"] for e in webhook_sink.events()] == ["consent.revoked"]
    deliveries = await sql("SELECT event_type, status FROM webhook_deliveries WHERE org_id=:o", o=org["id"])
    assert ("verification.completed", "cancelled") in [tuple(d) for d in deliveries]
    # 4. the business can't re-send it
    wid = (await sql("SELECT id, endpoint_id FROM webhook_deliveries WHERE org_id=:o AND status='cancelled'",
                     o=org["id"]))[0]
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/webhooks/{wid[1]}/deliveries/{wid[0]}/retry",
                          headers=owner["headers"])
    assert r.status_code == 403
    # 5. dashboard shows the same redaction
    d = (await client.get(f"/api/v1/business/organisations/{org['id']}/subjects/{v['subject_id']}",
                          headers=owner["headers"])).json()
    assert d["consent"]["status"] == "revoked" and "first_name" not in d and d["checks"][0]["redacted"] is True
    # 6. the user sees it as revoked
    apps = (await client.get("/api/v1/connected-apps", headers=person["headers"])).json()
    assert apps[0]["status"] == "revoked"


# ---------------------------------------------------------------------------
# Person not on FOID → later creates an account
# ---------------------------------------------------------------------------

async def test_subject_linked_when_person_joins_foid(client: httpx.AsyncClient, live_mock_provider: None) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    nin = "31234567890"
    body = {"number": nin, "first_name": "Ada", "last_name": "Obi", "email": "ada.later@example.com",
            "customer_ref": "lead-9", "consent": CONSENT}
    r = await client.post(f"{OPEN}/checks/nin", json=body, headers=org["h"]["live"])
    assert r.json()["status"] == "passed", r.text
    subject_id = r.json()["subject_id"]
    # same person in the business's sandbox — must never be linked to the real account
    await client.post(f"{OPEN}/checks/nin", json={**body, "customer_ref": "sandbox-9"}, headers=org["h"]["test"])

    # Someone signs up with the same NIN but a different email → NOT linked (NIN alone isn't proof).
    imposter = await make_user(client, nin=nin, email="imposter@example.com")
    assert (await client.get("/api/v1/connected-apps", headers=imposter["headers"])).json() == []

    # The real person signs up with the same NIN + the email the business has, then verifies the email.
    person = await make_user(client, nin=nin, email="ada.later@example.com", verify_email=False)
    assert (await client.get("/api/v1/connected-apps", headers=person["headers"])).json() == []
    code = "123456"
    from app.core.security import hash_refresh_token
    await sql("UPDATE email_verification_tokens SET code_hash=:h WHERE user_id=:u", h=hash_refresh_token(code),
              u=person["id"])
    r = await client.post("/api/v1/auth/verify-email", json={"email": person["email"], "code": code})
    assert r.status_code == 200, r.text

    apps = (await client.get("/api/v1/connected-apps", headers=person["headers"])).json()
    assert len(apps) == 1 and apps[0]["org_id"] == org["id"] and apps[0]["sandbox"] is False
    assert apps[0]["verified_before_joining_foid"] is True and apps[0]["checks"][0]["type"] == "nin"
    notes = (await client.get("/api/v1/notifications", headers=person["headers"])).json()
    assert any("verified you through FOID" in n["message"] for n in notes)

    s = (await client.get(f"{OPEN}/subjects/{subject_id}", headers=org["h"]["live"])).json()
    assert s["has_foid_account"] is True
    # Linking alone doesn't give the business FOID data:
    r = await client.get(f"{OPEN}/subjects/{subject_id}/trust-report", headers=org["h"]["live"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "scope_not_granted"

    # The person can now revoke the business that verified them before they joined.
    await client.delete(f"/api/v1/connected-apps/{org['id']}", headers=person["headers"])
    r = await client.get(f"{OPEN}/subjects/{subject_id}", headers=org["h"]["live"])
    assert r.json()["error"]["code"] == "consent_revoked"


async def test_existing_foid_user_checked_by_business_gets_linked(client: httpx.AsyncClient,
                                                                   live_mock_provider: None) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    person = await make_user(client, nin="41234567890", email="known@example.com")
    r = await client.post(f"{OPEN}/checks/nin", headers=org["h"]["live"],
                          json={"number": "41234567890", "first_name": "Ada", "last_name": "Obi",
                                "email": "known@example.com", "consent": CONSENT})
    assert r.json()["status"] == "passed"
    apps = (await client.get("/api/v1/connected-apps", headers=person["headers"])).json()
    assert [a["org_id"] for a in apps] == [org["id"]]


# ---------------------------------------------------------------------------
# Trust report, erasure
# ---------------------------------------------------------------------------

async def test_trust_report_requires_financial_scope(client: httpx.AsyncClient) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    person = await make_user(client)
    v = await _hosted(client, org, ["nin"], scopes=["financial"])
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"
    await client.post(f"{hs}/consent", json={"accept": True})
    await client.post(f"{hs}/share-foid", headers=person["headers"])
    r = await client.get(f"{OPEN}/subjects/{v['subject_id']}/trust-report", headers=org["h"]["test"])
    report = r.json()
    assert r.status_code == 200, r.text
    assert report["credential_state"] == "active" and "score" not in report
    assert 0 <= report["verification_completeness"] <= 100


async def test_delete_subject_erases_everything(client: httpx.AsyncClient, stub_face_verify: None) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    v = await _hosted(client, org, ["liveness"], customer_ref="erase-me")
    hs = f"/api/v1/hosted/sessions/{v['client_token']}"
    await client.post(f"{hs}/consent", json={"accept": True})
    sid = (await client.post(f"{hs}/liveness/start")).json()["session_id"]
    finish_liveness(sid)
    await client.post(f"{hs}/liveness/{sid}/complete")
    r = await client.delete(f"{OPEN}/subjects/{v['subject_id']}", headers=org["h"]["test"])
    assert r.status_code == 204
    for table in ("subjects", "check_results", "consent_grants", "subject_faces", "verifications",
                  "used_liveness_nonces"):
        col = "id" if table == "subjects" else "subject_id"
        assert await sql(f"SELECT 1 FROM {table} WHERE {col}=:s", s=v["subject_id"]) == [], table


async def test_webhook_secret_encrypted_and_test_endpoint(client: httpx.AsyncClient, webhook_sink: WebhookSink) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    secret = await _webhook(client, owner, org)
    row = (await sql("SELECT id, secret_enc FROM webhook_endpoints WHERE org_id=:o", o=org["id"]))[0]
    assert secret not in row[1] and decrypt_str(row[1]) == secret
    r = await client.post(f"/api/v1/business/organisations/{org['id']}/webhooks/{row[0]}/test", headers=owner["headers"])
    assert r.json()["status"] == "delivered" and _verify_signature(secret, webhook_sink.requests[-1])


async def test_credential_state_change_reaches_monitoring_lender(client: httpx.AsyncClient,
                                                                webhook_sink: WebhookSink) -> None:
    owner = await make_member(client)
    lender = await make_org(client, owner)
    other = await make_org(client, owner)            # identity-only business: must NOT be told
    await _webhook(client, owner, lender)
    await _webhook(client, owner, other)
    person = await make_user(client)
    for org, scopes in ((lender, ["financial"]), (other, [])):
        v = await _hosted(client, org, ["nin"], scopes=scopes)
        hs = f"/api/v1/hosted/sessions/{v['client_token']}"
        await client.post(f"{hs}/consent", json={"accept": True})
        await client.post(f"{hs}/share-foid", headers=person["headers"])
    await deliver_webhooks()
    webhook_sink.requests.clear()

    r = await client.post("/api/v1/credentials/trigger", json={"event": "missed_repayment"}, headers=person["headers"])
    assert r.status_code == 200, r.text
    await deliver_webhooks()
    events = webhook_sink.events()
    assert [e["type"] for e in events] == ["credential.state_changed"]
    assert events[0]["data"]["previous_state"] == "active" and events[0]["data"]["credential_state"] == "under_review"

    # after revoking, the lender hears nothing more
    await client.delete(f"/api/v1/connected-apps/{lender['id']}", headers=person["headers"])
    await deliver_webhooks()
    webhook_sink.requests.clear()
    await client.post("/api/v1/credentials/trigger", json={"event": "review_cleared"}, headers=person["headers"])
    await deliver_webhooks()
    assert webhook_sink.events() == []
