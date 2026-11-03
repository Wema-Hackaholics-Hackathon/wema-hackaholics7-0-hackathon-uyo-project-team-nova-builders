"""Webhook URLs can't be used to make FOID call its own network (SSRF)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import get_settings
from app.services import webhook_urls
from tests.conftest import WebhookSink, make_member, make_org

BIZ = "/api/v1/business/organisations"


async def _setup(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    owner = await make_member(client)
    return owner, await make_org(client, owner)


async def _create(client: httpx.AsyncClient, owner: dict[str, Any], org: dict[str, Any], url: str, env: str = "test") -> httpx.Response:
    return await client.post(f"{BIZ}/{org['id']}/webhooks", json={"env": env, "url": url}, headers=owner["headers"])


@pytest.mark.parametrize(("env", "url"), [
    ("live", "http://hooks.example.com/foid"),          # live is https only
    ("live", "https://localhost/foid"),                  # no localhost in live
    ("live", "https://127.0.0.1/foid"),
    ("live", "https://[::ffff:127.0.0.1]/foid"),         # IPv4-mapped loopback
    ("test", "http://10.0.0.5/foid"),                    # private ranges, any env
    ("test", "http://192.168.1.20:8080/foid"),
    ("test", "http://172.16.0.1/foid"),
    ("test", "http://100.64.0.1/foid"),                  # carrier-grade NAT
    ("test", "http://169.254.169.254/latest/meta-data"), # cloud metadata
    ("test", "http://[fd00::1]/foid"),                   # IPv6 unique-local
    ("test", "http://0.0.0.0/foid"),
    ("test", "https://redis.internal/foid"),             # internal names
    ("test", "https://printer.local/foid"),
    ("test", "http://intranet/foid"),                    # single label
    ("test", "https://user:pw@hooks.example.com/foid"),  # credentials in the URL
])
async def test_unsafe_urls_refused(client: httpx.AsyncClient, env: str, url: str) -> None:
    owner, org = await _setup(client)
    r = await _create(client, owner, org, url, env)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_webhook_url"


async def test_safe_urls_accepted(client: httpx.AsyncClient) -> None:
    owner, org = await _setup(client)
    assert (await _create(client, owner, org, "https://hooks.example.com/foid", "live")).status_code == 201
    assert (await _create(client, owner, org, "http://hooks.example.com/foid", "test")).status_code == 201
    # a developer's own machine, test mode only
    assert (await _create(client, owner, org, "http://localhost:3100/webhooks/foid", "test")).status_code == 201
    assert (await _create(client, owner, org, "http://127.0.0.1:3200/webhooks/foid", "test")).status_code == 201


async def test_localhost_can_be_switched_off(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "WEBHOOK_ALLOW_LOCALHOST", False)
    owner, org = await _setup(client)
    r = await _create(client, owner, org, "http://localhost:3100/webhooks/foid", "test")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_webhook_url"


async def test_production_refuses_localhost_by_default(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ENV", "production")
    monkeypatch.setattr(get_settings(), "WEBHOOK_ALLOW_LOCALHOST", None)
    owner, org = await _setup(client)
    assert (await _create(client, owner, org, "http://localhost:3100/h", "test")).status_code == 400


async def test_update_is_checked_too(client: httpx.AsyncClient) -> None:
    owner, org = await _setup(client)
    hook = (await _create(client, owner, org, "https://hooks.example.com/foid")).json()
    r = await client.patch(f"{BIZ}/{org['id']}/webhooks/{hook['id']}", json={"url": "http://169.254.169.254/"},
                           headers=owner["headers"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_webhook_url"


def _resolve_to(monkeypatch: pytest.MonkeyPatch, *addrs: str) -> None:
    async def fake(host: str, port: int) -> list[str]:
        return list(addrs)
    monkeypatch.setattr(webhook_urls, "resolve", fake)


async def _send_test(client: httpx.AsyncClient, owner: dict[str, Any], org: dict[str, Any], hook: dict[str, Any]) -> dict[str, Any]:
    r = await client.post(f"{BIZ}/{org['id']}/webhooks/{hook['id']}/test", headers=owner["headers"])
    assert r.status_code == 200, r.text
    return r.json()


async def test_delivery_pins_the_checked_address(client: httpx.AsyncClient, webhook_sink: WebhookSink,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    owner, org = await _setup(client)
    hook = (await _create(client, owner, org, "https://hooks.example.com:8443/foid?x=1")).json()
    _resolve_to(monkeypatch, "93.184.216.34")
    d = await _send_test(client, owner, org, hook)
    assert d["status"] == "delivered"
    req = webhook_sink.requests[-1]
    assert str(req.url) == "https://93.184.216.34:8443/foid?x=1"       # connects to the address we checked
    assert req.headers["Host"] == "hooks.example.com:8443"
    assert req.extensions["sni_hostname"] == "hooks.example.com"        # TLS still checks the real name


@pytest.mark.parametrize("addrs", [("10.0.0.7",), ("169.254.169.254",), ("93.184.216.34", "127.0.0.1"), ("::1",)])
async def test_delivery_refused_when_dns_points_inside(client: httpx.AsyncClient, webhook_sink: WebhookSink,
                                                       monkeypatch: pytest.MonkeyPatch, addrs: tuple[str, ...]) -> None:
    """A public name saved earlier that now resolves to an internal address (DNS rebinding)."""
    owner, org = await _setup(client)
    hook = (await _create(client, owner, org, "https://hooks.example.com/foid", "live")).json()
    _resolve_to(monkeypatch, *addrs)
    before = len(webhook_sink.requests)
    d = await _send_test(client, owner, org, hook)
    assert d["status"] != "delivered" and d["last_error"].startswith("blocked:")
    assert len(webhook_sink.requests) == before                          # nothing was sent


async def test_localhost_delivery_works_in_test_mode(client: httpx.AsyncClient, webhook_sink: WebhookSink,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    owner, org = await _setup(client)
    hook = (await _create(client, owner, org, "http://localhost:3100/webhooks/foid")).json()
    _resolve_to(monkeypatch, "127.0.0.1", "::1")
    d = await _send_test(client, owner, org, hook)
    assert d["status"] == "delivered"
    assert str(webhook_sink.requests[-1].url) == "http://127.0.0.1:3100/webhooks/foid"
