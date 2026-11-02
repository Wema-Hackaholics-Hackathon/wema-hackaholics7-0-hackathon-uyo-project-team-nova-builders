"""Billing per business with Bachs (checkout mocked, webhook signed like Bachs does)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from datetime import datetime

import httpx
import pytest

from app.config import get_settings
from app.services import bachs_service
from tests.conftest import make_member, make_org, sql

BIZ = "/api/v1/business/organisations"
HOOK = "/api/v1/wallet/bachs-webhook"
SECRET = "whsec_bachs_test"


@pytest.fixture
def bachs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Payments configured; checkout sessions recorded instead of calling Bachs."""
    monkeypatch.setattr(get_settings(), "BACHS_API_KEY", "sk_sandbox_test")
    monkeypatch.setattr(get_settings(), "BACHS_WEBHOOK_SECRET", SECRET)
    sessions: list[dict[str, Any]] = []

    async def fake(**kw: Any) -> dict[str, Any]:
        sessions.append(kw)
        return {"checkout_url": f"https://sandbox-checkout.bachs.io/{kw['reference']}"}

    monkeypatch.setattr(bachs_service, "create_checkout_session", fake)
    return sessions


async def _webhook(client: httpx.AsyncClient, reference: str, amount: str, secret: str = SECRET) -> httpx.Response:
    body = json.dumps({"type": "collection.succeeded", "data": {"reference": reference, "amount": amount}})
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return await client.post(HOOK, content=body, headers={"X-Bachs-Signature-V2": f"t={ts},v1={sig}",
                                                          "Content-Type": "application/json"})


async def _billing(client: httpx.AsyncClient, owner: dict[str, Any], org_id: str) -> dict[str, Any]:
    return (await client.get(f"{BIZ}/{org_id}/billing", headers=owner["headers"])).json()


async def test_plans_usage_and_unconfigured_payments(client: httpx.AsyncClient, live_mock_provider: None) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner, live=True)
    plans = (await client.get("/api/v1/business/plans", headers=owner["headers"])).json()
    assert [p["code"] for p in plans] == ["starter", "growth", "business", "enterprise"]

    consent = {"obtained": True, "purpose": "Account opening"}
    for env in ("live", "test", "test"):
        await client.post("/api/open/v1/checks/nin", headers=org["h"][env], json={
            "first_name": "Ada", "last_name": "Obi", "number": "12345678900", "consent": consent})
    b = await _billing(client, owner, org["id"])
    assert b["plan"]["code"] == "starter" and b["usage"]["limit"] == 500
    assert b["usage"]["live"]["total"] == 1 and b["usage"]["test"]["total"] == 2            # only live is billable

    r = await client.post(f"{BIZ}/{org['id']}/billing/checkout", json={"plan_code": "business"}, headers=owner["headers"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "payments_not_configured"

    dev = await make_member(client)
    await client.post(f"{BIZ}/{org['id']}/members", json={"email": dev["email"], "role": "developer"}, headers=owner["headers"])
    assert (await client.get(f"{BIZ}/{org['id']}/billing", headers=dev["headers"])).status_code == 403


async def test_upgrade_paid_only_by_signed_webhook(client: httpx.AsyncClient, bachs: list[dict[str, Any]]) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    url = f"{BIZ}/{org['id']}/billing/checkout"
    assert (await client.post(url, json={"plan_code": "enterprise"}, headers=owner["headers"])).json()["error"]["code"] == "contact_sales"

    first = (await client.post(url, json={"plan_code": "growth"}, headers=owner["headers"])).json()
    r = (await client.post(url, json={"plan_code": "business"}, headers=owner["headers"])).json()
    assert r["checkout_url"].startswith("https://sandbox-checkout.bachs.io/inv_") and r["invoice"]["amount_ngn"] == 420_000
    sent = bachs[-1]
    assert sent["amount_ngn"] == 420_000 and sent["success_url"].endswith(f"/billing?invoice={r['invoice']['id']}")
    b = await _billing(client, owner, org["id"])
    assert [i["id"] for i in b["invoices"]] == [r["invoice"]["id"]]                       # earlier attempt voided
    assert first["invoice"]["id"] not in [i["id"] for i in b["invoices"]]
    assert b["plan"]["code"] == "starter"                                                  # nothing paid yet

    ref = sent["reference"]
    assert (await _webhook(client, ref, "420000.00", secret="wrong")).status_code == 400   # forged
    assert (await _webhook(client, ref, "1.00")).json()["status"] == "amount_mismatch"
    assert (await client.get(f"{BIZ}/{org['id']}/invoices/{r['invoice']['id']}", headers=owner["headers"])).json()["status"] == "open"

    assert (await _webhook(client, ref, "420000.00")).json()["status"] == "ok"
    assert (await _webhook(client, ref, "420000.00")).json()["status"] == "already_paid"   # Bachs retries are harmless
    b = await _billing(client, owner, org["id"])
    assert b["plan"]["code"] == "business" and b["usage"]["limit"] == 15_000
    assert b["invoices"][0]["status"] == "paid" and b["invoices"][0]["paid_at"]

    pdf = await client.get(f"{BIZ}/{org['id']}/invoices/{r['invoice']['id']}/pdf", headers=owner["headers"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    r = await client.post(url, json={"plan_code": "starter"}, headers=owner["headers"])
    assert r.json()["checkout_url"] is None and (await _billing(client, owner, org["id"]))["plan"]["code"] == "starter"


async def test_renewal_invoice_opens_once_and_extends_period(client: httpx.AsyncClient, bachs: list[dict[str, Any]]) -> None:
    owner = await make_member(client)
    org = await make_org(client, owner)
    r = (await client.post(f"{BIZ}/{org['id']}/billing/checkout", json={"plan_code": "growth"}, headers=owner["headers"])).json()
    await _webhook(client, bachs[-1]["reference"], "150000.00")
    await sql("UPDATE organisations SET plan_period_end=:t WHERE id=:o", t=datetime(2000, 2, 1), o=org["id"])

    from app.config import _get_session_factory
    from app.services.billing_service import open_renewals
    async with _get_session_factory()() as db:
        assert await open_renewals(db) >= 1
        assert await open_renewals(db) == 0                                               # not twice
    inv = next(i for i in (await _billing(client, owner, org["id"]))["invoices"] if i["kind"] == "renewal")
    assert inv["status"] == "open" and inv["period_start"].startswith("2000-02-01") and r["invoice"]["kind"] == "plan_change"

    pay = (await client.post(f"{BIZ}/{org['id']}/invoices/{inv['id']}/pay", headers=owner["headers"])).json()
    assert pay["checkout_url"]
    assert (await _webhook(client, bachs[-1]["reference"], "150000.00")).json()["status"] == "ok"
    (row,) = await sql("SELECT plan_period_end FROM organisations WHERE id=:o", o=org["id"])
    assert str(row[0]).startswith("2000-03-02")                                           # +30 days from the old end
