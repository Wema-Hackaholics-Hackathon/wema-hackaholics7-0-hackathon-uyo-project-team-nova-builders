"""Go live (KYB): business uploads details + documents, FOID admin approves or rejects."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services import kyb_service
from tests.conftest import make_member, make_user, sql

BIZ = "/api/v1/business/organisations"
PDF = b"%PDF-1.7\n" + b"x" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 500
DETAILS = {"rc_number": "RC1234567", "tin": "12345678-0001", "registered_address": "12 Marina Road, Lagos Island, Lagos"}


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def fake_send(*, to: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append((to, subject))

    monkeypatch.setattr(kyb_service, "send_email", fake_send)
    return sent


async def _setup(client: httpx.AsyncClient) -> tuple[dict[str, Any], str]:
    owner = await make_member(client)
    org_id = (await client.get(BIZ, headers=owner["headers"])).json()[0]["id"]   # created at signup
    return owner, org_id


async def _upload(client: httpx.AsyncClient, h: dict[str, str], org_id: str, type_: str,
                  data: bytes = PDF, name: str = "doc.pdf") -> httpx.Response:
    return await client.post(f"{BIZ}/{org_id}/kyb/documents", headers=h, data={"type": type_},
                             files={"file": (name, data, "application/octet-stream")})


async def _admin(client: httpx.AsyncClient) -> dict[str, str]:
    admin = await make_user(client)
    await sql("UPDATE users SET is_admin=TRUE WHERE id=:u", u=admin["id"])
    return admin["headers"]


async def test_uploads_are_checked_and_stored_encrypted(client: httpx.AsyncClient) -> None:
    owner, org_id = await _setup(client)
    h = owner["headers"]
    kyb = (await client.get(f"{BIZ}/{org_id}/kyb", headers=h)).json()
    assert kyb["status"] == "not_submitted" and kyb["editable"] and kyb["documents"] == []
    assert set(kyb["missing"]) == {"rc_number", "tin", "registered_address", *kyb_service.REQUIRED}

    r = await _upload(client, h, org_id, "cac_certificate", b"hello, not a pdf", "fake.pdf")
    assert r.status_code == 415                                        # checked by content, not by name
    r = await _upload(client, h, org_id, "cac_certificate", b"%PDF-" + b"0" * kyb_service.MAX_BYTES)
    assert r.status_code == 413
    assert (await _upload(client, h, org_id, "selfie")).status_code == 422

    r = await _upload(client, h, org_id, "cac_certificate", PDF, "../../etc/passwd.pdf")
    assert r.status_code == 201 and r.json()["filename"] == "passwd.pdf" and r.json()["mime"] == "application/pdf"
    r = await _upload(client, h, org_id, "cac_certificate", PNG, "scan.png")    # replaces, doesn't add
    assert r.status_code == 201 and r.json()["mime"] == "image/png"
    docs = (await client.get(f"{BIZ}/{org_id}/kyb", headers=h)).json()["documents"]
    assert [(d["type"], d["filename"]) for d in docs] == [("cac_certificate", "scan.png")]

    (blob,) = (await sql("SELECT data_enc FROM kyb_documents WHERE org_id=:o", o=org_id))[0]
    assert PNG not in bytes(blob) and b"\x89PNG" not in bytes(blob)    # encrypted at rest


async def test_roles_and_completeness(client: httpx.AsyncClient) -> None:
    owner, org_id = await _setup(client)
    dev, admin_m = await make_member(client), await make_member(client)
    for m, role in ((dev, "developer"), (admin_m, "admin")):
        r = await client.post(f"{BIZ}/{org_id}/members", json={"email": m["email"], "role": role}, headers=owner["headers"])
        assert r.status_code == 201
    assert (await _upload(client, dev["headers"], org_id, "memart")).status_code == 403
    assert (await _upload(client, admin_m["headers"], org_id, "memart")).status_code == 201

    r = await client.post(f"{BIZ}/{org_id}/kyb", headers=owner["headers"])
    assert r.status_code == 422 and "cac_certificate" in r.json()["error"]["details"]["missing"]

    await client.put(f"{BIZ}/{org_id}/kyb/details", json=DETAILS, headers=admin_m["headers"])
    for t in kyb_service.REQUIRED:
        await _upload(client, admin_m["headers"], org_id, t)
    assert (await client.post(f"{BIZ}/{org_id}/kyb", headers=admin_m["headers"])).status_code == 403   # owner attests
    assert (await client.get(f"{BIZ}/{org_id}/kyb", headers=owner["headers"])).json()["missing"] == []


async def test_review_reject_resubmit_approve(client: httpx.AsyncClient, mails: list[tuple[str, str]]) -> None:
    owner, org_id = await _setup(client)
    h = owner["headers"]
    await client.put(f"{BIZ}/{org_id}/kyb/details", json=DETAILS, headers=h)
    for t in kyb_service.REQUIRED:
        await _upload(client, h, org_id, t)
    r = await client.post(f"{BIZ}/{org_id}/kyb", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "pending" and not r.json()["editable"]
    name = await _org_name(client, h, org_id)
    assert mails[-1] == (owner["email"], f"We've received {name}'s documents")

    assert (await _upload(client, h, org_id, "licence")).status_code == 409          # locked while in review
    assert (await client.put(f"{BIZ}/{org_id}/kyb/details", json=DETAILS, headers=h)).status_code == 409
    assert (await client.post(f"{BIZ}/{org_id}/api-keys", json={"env": "live"}, headers=h)).status_code == 403

    admin = await _admin(client)
    assert (await client.get(f"/api/v1/admin/organisations/{org_id}/kyb", headers=h)).status_code == 401   # console token
    review = (await client.get(f"/api/v1/admin/organisations/{org_id}/kyb", headers=admin)).json()
    doc = review["documents"][0]
    r = await client.get(f"/api/v1/admin/organisations/{org_id}/kyb/documents/{doc['id']}", headers=admin)
    assert r.status_code == 200 and r.content == PDF and "attachment" in r.headers["content-disposition"]

    assert (await client.post(f"/api/v1/admin/organisations/{org_id}/kyb", json={"approve": False},
                              headers=admin)).status_code == 422               # a rejection needs a reason
    r = await client.post(f"/api/v1/admin/organisations/{org_id}/kyb",
                          json={"approve": False, "note": "CAC status report is older than 12 months"}, headers=admin)
    assert r.json()["kyb_status"] == "rejected"
    kyb = (await client.get(f"{BIZ}/{org_id}/kyb", headers=h)).json()
    assert kyb["note"] == "CAC status report is older than 12 months" and kyb["editable"]
    assert "Action needed" in mails[-1][1]

    assert (await _upload(client, h, org_id, "cac_status")).status_code == 201       # fix + resubmit
    assert (await client.post(f"{BIZ}/{org_id}/kyb", headers=h)).json()["status"] == "pending"
    r = await client.post(f"/api/v1/admin/organisations/{org_id}/kyb", json={"approve": True}, headers=admin)
    assert r.json() == {"id": org_id, "kyb_status": "approved", "live_enabled": True}
    assert "approved for Live" in mails[-1][1]
    assert (await client.post(f"/api/v1/admin/organisations/{org_id}/kyb", json={"approve": True},
                              headers=admin)).status_code == 409               # nothing pending
    r = await client.post(f"{BIZ}/{org_id}/api-keys", json={"env": "live"}, headers=h)
    assert r.status_code == 201 and r.json()["secret"].startswith("FOID_LIVE_")


async def _org_name(client: httpx.AsyncClient, h: dict[str, str], org_id: str) -> str:
    return (await client.get(f"{BIZ}/{org_id}", headers=h)).json()["name"]
