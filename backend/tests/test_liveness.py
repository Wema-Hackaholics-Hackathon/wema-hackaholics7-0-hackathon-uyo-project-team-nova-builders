"""First-party liveness + face enrolment (/api/v1/auth/me/liveness/*)."""

from __future__ import annotations

import asyncio

import cv2
import httpx
import numpy as np

from tests.conftest import FACE_PNG, finish_liveness, make_user, sql

LV = "/api/v1/auth/me/liveness"


def _frame_rgba() -> bytes:
    """A 320x240 raw RGBA frame (canvas ImageData layout) with the fixture face in the middle."""
    face = cv2.imdecode(np.frombuffer(FACE_PNG, np.uint8), cv2.IMREAD_COLOR)
    face = cv2.resize(face, (200, 200), interpolation=cv2.INTER_CUBIC)
    frame = np.full((240, 320, 3), 200, np.uint8)
    frame[20:220, 60:260] = face
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA).tobytes()


def _frame_url(sid: str) -> str:
    return f"/api/v1/liveness/sessions/{sid}/frame?w=320&h=240"


async def _enrol(client: httpx.AsyncClient, user: dict[str, object], receipt: str) -> httpx.Response:
    r = await client.post(f"{LV}/start", json={"purpose": "enrol", "consent": True}, headers=user["headers"])  # type: ignore[arg-type]
    finish_liveness(r.json()["session_id"], receipt=receipt)
    return await client.post(f"{LV}/{r.json()['session_id']}/complete", headers=user["headers"])  # type: ignore[arg-type]


async def test_start_rules(client: httpx.AsyncClient) -> None:
    unverified = await make_user(client, verify_email=False)
    r = await client.post(f"{LV}/start", json={"purpose": "enrol", "consent": True}, headers=unverified["headers"])
    assert r.status_code == 403

    user = await make_user(client)
    h = user["headers"]
    assert (await client.post(f"{LV}/start", json={"purpose": "enrol"}, headers=h)).status_code == 400
    assert (await client.post(f"{LV}/start", json={"purpose": "verify"}, headers=h)).status_code == 409
    r = await client.post(f"{LV}/start", json={"purpose": "enrol", "consent": True}, headers=h)
    assert r.status_code == 201
    assert set(r.json()["challenges"]) <= {"turn_left", "turn_right", "open_mouth"}
    assert "eyJ" not in r.text   # the signed ticket never leaves the server


async def test_frames_run_through_the_real_engine(client: httpx.AsyncClient) -> None:
    user = await make_user(client)
    h = user["headers"]
    sid = (await client.post(f"{LV}/start", json={"purpose": "enrol", "consent": True}, headers=h)).json()["session_id"]

    r = await client.post(_frame_url(sid), content=b"too-short")
    assert r.status_code == 400   # wrong byte count for 320x240 RGBA
    # no login needed for frames: the nonce is the credential
    r = await client.post(_frame_url(sid), content=_frame_rgba())
    assert r.status_code == 200 and r.json()["status"] == "in_progress" and r.json()["face_count"] == 1, r.text
    assert (await client.post(f"{LV}/{sid}/complete", headers=h)).status_code == 409
    assert (await client.post(_frame_url("nope"), content=_frame_rgba())).status_code == 404

    codes = sorted(x.status_code for x in await asyncio.gather(
        *[client.post(_frame_url(sid), content=_frame_rgba()) for _ in range(2)]))
    assert codes in ([200, 429], [200, 200])


async def test_failed_receipt_is_rejected_by_the_sdk(client: httpx.AsyncClient) -> None:
    from app.services import liveness_service as ls

    user = await make_user(client)
    sid = (await client.post(f"{LV}/start", json={"purpose": "enrol", "consent": True},
                             headers=user["headers"])).json()["session_id"]
    # A genuinely signed receipt from a session that did NOT pass, presented as passed.
    key = ls.get_signing_key()
    import faceliveness
    engine = faceliveness.Engine.from_ticket(key.issue_ticket(["open_mouth"]), key.public_key, step_timeout_ms=1)
    frame = np.frombuffer(_frame_rgba(), np.uint8).reshape(240, 320, 4)
    for t in (0, 50, 100):
        engine.process(frame, t, format="rgba")
    ls._sessions[sid].final = ls.FinalResult(True, None, engine.receipt(key), FACE_PNG)
    r = await client.post(f"{LV}/{sid}/complete", headers=user["headers"])
    assert r.status_code == 422 and "did not pass" in r.text


async def test_enrol_verify_replay_delete(client: httpx.AsyncClient, stub_face_verify: None) -> None:
    user = await make_user(client)
    h = user["headers"]
    r = await _enrol(client, user, "nonce-a")
    assert r.status_code == 200 and r.json()["enrolled"] is True, r.text

    claims = (await client.get("/api/v1/credentials/me", headers=h)).json()["claims"]
    assert claims["identity_verified"] is True
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["liveness_verified_at"] and me["liveness_selfie_url"].endswith("/liveness/face")
    assert (await client.get(f"{LV}/face", headers=h)).content == FACE_PNG
    row = (await sql("SELECT template_enc FROM face_enrolments WHERE user_id=:u", u=user["id"]))[0]
    assert bytes(row[0])[:5] == b"gAAAA"   # Fernet-encrypted

    assert (await _enrol(client, user, "nonce-a")).status_code == 409   # replayed receipt

    sid = (await client.post(f"{LV}/start", json={"purpose": "verify"}, headers=h)).json()["session_id"]
    finish_liveness(sid, receipt="nonce-b")
    r = await client.post(f"{LV}/{sid}/complete", headers=h)
    assert r.json()["matched"] is True and r.json()["score"] > 0.99

    other = cv2.imencode(".png", np.full((112, 112, 3), 90, np.uint8))[1].tobytes()
    sid = (await client.post(f"{LV}/start", json={"purpose": "verify"}, headers=h)).json()["session_id"]
    finish_liveness(sid, png=other, receipt="nonce-c")
    assert (await client.post(f"{LV}/{sid}/complete", headers=h)).json()["matched"] is False

    assert (await client.delete(f"{LV}/enrolment", headers=h)).status_code == 204
    assert (await client.get(f"{LV}/status", headers=h)).json()["enrolled"] is False
    claims = (await client.get("/api/v1/credentials/me", headers=h)).json()["claims"]
    assert claims["identity_verified"] is False


async def test_signup_survives_email_provider_failure(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A rejected/failed email must not turn a created account into a 500."""
    from app.config import get_settings
    from app.services import email_service

    async def boom(**_kw: object) -> None:
        raise RuntimeError("Invalid `to` field")
    monkeypatch.setattr(get_settings(), "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service, "_send_via_resend", boom)
    r = await client.post("/api/v1/auth/signup", json=dict(first_name="Ada", last_name="Obi", nin="69999999990",
                                                          email="bounce@example.com", password="Passw0rd!x"))
    assert r.status_code == 201, r.text
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "bounce@example.com"})
    assert r.status_code == 200



# ---------------------------------------------------------------------------
# Continue on another device: single-use, 10-minute link
# ---------------------------------------------------------------------------

async def test_handoff_phone_completes_and_laptop_sees_it(client: httpx.AsyncClient, stub_face_verify: None) -> None:
    user = await make_user(client)
    h = user["headers"]
    assert (await client.post(f"{LV}/handoff", json={"purpose": "enrol"}, headers=h)).status_code == 400  # consent
    r = await client.post(f"{LV}/handoff", json={"purpose": "enrol", "consent": True}, headers=h)
    assert r.status_code == 201, r.text
    handoff = r.json()
    assert 590 <= handoff["seconds_left"] <= 600
    token = handoff["url"].rsplit("/", 1)[1]

    # phone: no Authorization header anywhere
    info = (await client.get(f"/api/v1/liveness/handoff/{token}")).json()
    assert info["status"] == "pending" and info["display_name"] == "Ada O."
    start = (await client.post(f"/api/v1/liveness/handoff/{token}/start")).json()
    assert (await client.get(f"{LV}/handoff/{handoff['handoff_id']}", headers=h)).json()["status"] == "in_progress"
    finish_liveness(start["session_id"], receipt="handoff-nonce")
    r = await client.post(f"/api/v1/liveness/handoff/{token}/complete", json={"session_id": start["session_id"]})
    assert r.json()["passed"] is True and r.json()["enrolled"] is True, r.text

    # laptop sees it
    st = (await client.get(f"{LV}/handoff/{handoff['handoff_id']}", headers=h)).json()
    assert st["status"] == "completed" and st["result"]["passed"] is True
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["liveness_verified_at"]
    # single use
    assert (await client.post(f"/api/v1/liveness/handoff/{token}/start")).status_code == 410


async def test_handoff_expires_and_new_link_cancels_old(client: httpx.AsyncClient) -> None:
    from app.services import liveness_handoff

    user = await make_user(client)
    h = user["headers"]
    first = (await client.post(f"{LV}/handoff", json={"purpose": "enrol", "consent": True}, headers=h)).json()
    second = (await client.post(f"{LV}/handoff", json={"purpose": "enrol", "consent": True}, headers=h)).json()
    old_token = first["url"].rsplit("/", 1)[1]
    r = await client.post(f"/api/v1/liveness/handoff/{old_token}/start")
    assert r.status_code == 410 and "cancelled" in r.json()["detail"]

    liveness_handoff._by_id[second["handoff_id"]].expires_at = 0   # simulate 10 minutes passing
    token = second["url"].rsplit("/", 1)[1]
    r = await client.post(f"/api/v1/liveness/handoff/{token}/start")
    assert r.status_code == 410 and "expired" in r.json()["detail"]
    assert (await client.get(f"{LV}/handoff/{second['handoff_id']}", headers=h)).json()["status"] == "expired"
    assert (await client.get("/api/v1/liveness/handoff/not-a-real-token")).status_code == 404
