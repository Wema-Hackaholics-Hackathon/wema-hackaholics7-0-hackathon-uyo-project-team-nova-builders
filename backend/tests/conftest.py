"""Shared fixtures: throwaway SQLite DB, ASGI client, helpers for users/orgs/keys.

Environment is set BEFORE the app is imported so settings pick it up.
Run:  cd backend && uv run pytest -q
"""

from __future__ import annotations

import os
import tempfile
import types
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

_TMP = tempfile.mkdtemp(prefix="foid-tests-")
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
    "ENV": "test",
    "RESEND_API_KEY": "",
    "GROQ_API_KEY": "",
    "SECRET_KEY": "test-secret",
})

import faceliveness  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.config import _get_session_factory, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import identity, liveness_service  # noqa: E402
from app.services.identity.mock import MockProvider  # noqa: E402
from app.utils.limiter import limiter  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
FACE_PNG = (FIXTURES / "astronaut_face_record.png").read_bytes()
limiter.enabled = False


@pytest.fixture(scope="session", autouse=True)
async def _db() -> None:
    await init_db()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def live_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let live-mode keys use the sandbox provider (tests only)."""
    monkeypatch.setitem(identity._LIVE_PROVIDERS, "mock", MockProvider)


@pytest.fixture
def stub_face_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real passed liveness session needs a live face on camera; stub ONLY the SDK verdict."""
    def fake(receipt: str, _pk: bytes, _png: bytes, **_kw: Any) -> Any:
        return types.SimpleNamespace(nonce=receipt, face_sha256="x", face_quality=0.8, real_score=0.9)
    monkeypatch.setattr(faceliveness, "verify_face_record", fake)


def finish_liveness(nonce: str, png: bytes = FACE_PNG, receipt: str | None = None) -> None:
    """Mark an in-memory liveness session as passed (receipt doubles as the nonce for the stub)."""
    liveness_service._sessions[nonce].final = liveness_service.FinalResult(True, None, receipt or f"r-{nonce}", png)


async def sql(statement: str, **params: Any) -> list[Any]:
    async with _get_session_factory()() as db:
        result = await db.execute(text(statement), params)  # raw SQL in tests
        rows = result.fetchall() if result.returns_rows else []
        await db.commit()
        return list(rows)


_counter = iter(range(10_000))


async def make_user(client: httpx.AsyncClient, *, nin: str | None = None, email: str | None = None,
                    first: str = "Ada", last: str = "Obi", verify_email: bool = True) -> dict[str, Any]:
    n = next(_counter)
    email = email or f"user{n}@example.com"
    nin = nin or f"{70000000000 + n}"
    r = await client.post("/api/v1/auth/signup", json=dict(first_name=first, last_name=last, nin=nin,
                                                          email=email, password="Passw0rd!x"))
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    if verify_email:
        await sql("UPDATE credentials SET claims=json_set(claims,'$.email_verified',json('true')) WHERE user_id=:u",
                  u=me["id"])
    return {"id": me["id"], "email": email, "nin": nin, "headers": headers}


async def make_org(client: httpx.AsyncClient, owner: dict[str, Any], *, live: bool = False) -> dict[str, Any]:
    r = await client.post("/api/v1/business/organisations", json={"name": f"Acme {next(_counter)}"},
                          headers=owner["headers"])
    assert r.status_code == 201, r.text
    org = r.json()
    if live:
        await sql("UPDATE organisations SET live_enabled=1, kyb_status='approved' WHERE id=:o", o=org["id"])
    keys: dict[str, str] = {}
    for env in (["test", "live"] if live else ["test"]):
        k = await client.post(f"/api/v1/business/organisations/{org['id']}/api-keys", json={"env": env},
                              headers=owner["headers"])
        assert k.status_code == 201, k.text
        keys[env] = k.json()["secret"]
    return {**org, "keys": keys, "h": {env: {"Authorization": f"Bearer {key}"} for env, key in keys.items()}}


class WebhookSink:
    """Captures webhook POSTs made by the delivery worker."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)

    def events(self) -> list[dict[str, Any]]:
        import json
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture
def webhook_sink(monkeypatch: pytest.MonkeyPatch) -> WebhookSink:
    from app.services import webhook_service

    sink = WebhookSink()
    factory: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(sink.handler))
    monkeypatch.setattr(webhook_service, "new_client", factory)
    return sink


async def deliver_webhooks() -> int:
    from app.services.webhook_service import deliver_due
    return await deliver_due(_get_session_factory())
