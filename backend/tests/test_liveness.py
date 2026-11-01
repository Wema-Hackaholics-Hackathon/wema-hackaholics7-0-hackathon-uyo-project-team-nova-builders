"""First-party liveness + face enrolment (/api/v1/auth/me/liveness/*)."""

from __future__ import annotations

import asyncio

import cv2
import httpx
import numpy as np

from tests.conftest import FACE_PNG, finish_liveness, make_user, sql

LV = "/api/v1/auth/me/liveness"


def _frame_jpeg() -> bytes:
    """A 320x240 camera-like frame with the fixture face in the middle."""
    face = cv2.imdecode(np.frombuffer(FACE_PNG, np.uint8), cv2.IMREAD_COLOR)
    face = cv2.resize(face, (200, 200), interpolation=cv2.INTER_CUBIC)
    frame = np.full((240, 320, 3), 200, np.uint8)
    frame[20:220, 60:260] = face
    return cv2.imencode(".jpg", frame)[1].tobytes()


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

    r = await client.post(f"{LV}/{sid}/frame", content=b"not-a-jpeg", headers=h)
    assert r.status_code == 422
    r = await client.post(f"{LV}/{sid}/frame", content=_frame_jpeg(), headers=h)
    assert r.status_code == 200 and r.json()["status"] == "in_progress" and r.json()["face_count"] == 1, r.text
    assert (await client.post(f"{LV}/{sid}/complete", headers=h)).status_code == 409
    assert (await client.post(f"{LV}/nope/frame", content=_frame_jpeg(), headers=h)).status_code == 404

    codes = sorted(x.status_code for x in await asyncio.gather(
        *[client.post(f"{LV}/{sid}/frame", content=_frame_jpeg(), headers=h) for _ in range(2)]))
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
    frame = cv2.imdecode(np.frombuffer(_frame_jpeg(), np.uint8), cv2.IMREAD_COLOR)
    for t in (0, 50, 100):
        engine.process(frame, t, format="bgr")
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
