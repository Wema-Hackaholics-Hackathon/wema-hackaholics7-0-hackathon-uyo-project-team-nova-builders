"""Business webhooks — signed, retried, and consent-aware.

enqueue_event()  writes one WebhookDelivery per matching endpoint (caller commits).
deliver_due()    sends due deliveries; webhook_loop() (started from main.py's
                 lifespan) runs it when an event is queued, and once a minute
                 for retries — it does not poll the database while idle.

Signature header (verify on the business side):
    FOID-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, f"{t}.{raw_body}")>

Consent: a delivery about a subject is CANCELLED at send time if the business no
longer holds an active consent grant for that subject — revocation stops data
immediately, even for events queued before it. The single exception is
`consent.revoked` itself, which tells the business to stop.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.crypto import decrypt_str
from app.models import ConsentGrant, WebhookDelivery, WebhookEndpoint
from app.services.webhook_urls import BlockedUrl, safe_target

EVENT_TYPES = [
    "verification.completed",
    "verification.cancelled",
    "verification.expired",
    "check.completed",
    "credential.state_changed",
    "consent.revoked",
    "subject.linked",
    "webhook.test",
]
_ALWAYS_DELIVER = {"consent.revoked", "webhook.test"}
_BACKOFF_SECS = [10, 30, 120, 600, 1800, 3600, 3 * 3600, 6 * 3600]
_TIMEOUT_SECS = 10
_BATCH = 20
_IDLE_CHECK_SECS = 60      # retries due later are picked up at least this often

# Set whenever an event is queued, so the sender wakes immediately instead of
# polling the database every few seconds while idle.
_wake: asyncio.Event | None = None


def _wake_event() -> asyncio.Event:
    global _wake
    if _wake is None:
        _wake = asyncio.Event()
    return _wake


def new_client() -> httpx.AsyncClient:
    """HTTP client used for deliveries (tests swap this for a mock transport)."""
    return httpx.AsyncClient()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def build_event(event_type: str, env: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "env": env,
        "created": int(time.time()),
        "data": data,
    }


async def enqueue_event(
    db: AsyncSession,
    *,
    org_id: str,
    env: str,
    event_type: str,
    data: dict[str, Any],
    subject_id: str | None = None,
) -> str:
    """Queue an event for every enabled endpoint of the org/env that subscribes to it."""
    event = build_event(event_type, env, data)
    from app.models import Organisation
    org = await db.get(Organisation, org_id)
    if org is None or org.status != "active":     # deactivated businesses get nothing
        return event["id"]
    endpoints = (await db.exec(
        select(WebhookEndpoint).where(
            WebhookEndpoint.org_id == org_id,
            WebhookEndpoint.env == env,
            WebhookEndpoint.enabled == True,  # noqa: E712
        )
    )).all()
    for ep in endpoints:
        if "*" in ep.events or event_type in ep.events:
            db.add(WebhookDelivery(
                org_id=org_id,
                endpoint_id=ep.id,
                event_id=event["id"],
                event_type=event_type,
                subject_id=subject_id,
                payload=event,
            ))
            _wake_event().set()
    return event["id"]


async def cancel_pending_for_subject(db: AsyncSession, org_id: str, subject_id: str) -> int:
    rows = (await db.exec(
        select(WebhookDelivery).where(
            WebhookDelivery.org_id == org_id,
            WebhookDelivery.subject_id == subject_id,
            WebhookDelivery.status == "pending",
        )
    )).all()
    for d in rows:
        if d.event_type in _ALWAYS_DELIVER:
            continue
        d.status = "cancelled"
        d.last_error = "consent revoked"
        db.add(d)
    return len(rows)


async def _consent_active(db: AsyncSession, org_id: str, subject_id: str) -> bool:
    row = (await db.exec(
        select(ConsentGrant.id).where(
            ConsentGrant.org_id == org_id,
            ConsentGrant.subject_id == subject_id,
            ConsentGrant.status == "active",
        )
    )).first()
    return row is not None


async def _send(client: httpx.AsyncClient, ep: WebhookEndpoint, payload: dict[str, Any]) -> tuple[int | None, str | None]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "FOID-Webhooks/1",
        "FOID-Signature": sign(decrypt_str(ep.secret_enc), int(time.time()), body),
        "FOID-Event-Id": str(payload["id"]),
    }
    try:
        # Re-check the URL and connect to the address we checked (no DNS rebinding, no redirects).
        target = await safe_target(ep.url, ep.env)
    except BlockedUrl as exc:
        return None, f"blocked: {exc}"[:300]
    if target.host_header:
        headers["Host"] = target.host_header
    extensions = {"sni_hostname": target.sni_hostname} if target.sni_hostname else None
    try:
        r = await client.post(target.url, content=body, headers=headers, timeout=_TIMEOUT_SECS,
                              follow_redirects=False, extensions=extensions)
        return r.status_code, None if r.is_success else r.text[:300]
    except httpx.HTTPError as exc:
        return None, str(exc)[:300]


async def attempt(db: AsyncSession, d: WebhookDelivery, client: httpx.AsyncClient) -> None:
    """Try one delivery now and record the outcome (caller commits)."""
    ep = await db.get(WebhookEndpoint, d.endpoint_id)
    if ep is None or not ep.enabled:
        d.status, d.last_error = "cancelled", "endpoint disabled"
    elif d.subject_id and d.event_type not in _ALWAYS_DELIVER and not await _consent_active(db, d.org_id, d.subject_id):
        d.status, d.last_error = "cancelled", "consent revoked"
    else:
        code, err = await _send(client, ep, d.payload)
        d.attempts += 1
        d.last_status_code, d.last_error = code, err
        if code is not None and 200 <= code < 300:
            d.status, d.delivered_at = "delivered", utcnow()
        elif d.attempts >= len(_BACKOFF_SECS):
            d.status = "failed"
            from app.services.console_inbox import notify
            await notify(db, d.org_id, "webhook_failing", "Webhook endpoint is failing",
                         f"{d.event_type} to {ep.url} failed after {d.attempts} tries ({code or err}).",
                         link="/api-keys", min_role="developer", ref=ep.id, once_per=timedelta(days=1))
        else:
            d.next_attempt_at = utcnow() + timedelta(seconds=_BACKOFF_SECS[d.attempts - 1])
    db.add(d)


async def deliver_due(session_factory: Any) -> int:
    async with session_factory() as db:
        now = utcnow()
        due = (await db.exec(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= now)
            .order_by(WebhookDelivery.next_attempt_at)  # pyright: ignore[reportArgumentType]
            .limit(_BATCH)
        )).all()
        if not due:
            return 0
        async with new_client() as client:
            for d in due:
                await attempt(db, d, client)
        await db.commit()
        return len(due)


async def webhook_loop() -> None:
    from app.config import _get_session_factory

    wake = _wake_event()
    await asyncio.sleep(5)
    while True:
        try:
            await deliver_due(_get_session_factory())
        except Exception as exc:   # never let the loop die
            print(f"[webhooks] error: {exc}", flush=True)
        # Sleep until something is queued (or the idle check for scheduled retries).
        try:
            await asyncio.wait_for(wake.wait(), timeout=_IDLE_CHECK_SECS)
        except TimeoutError:
            pass
        wake.clear()
        await asyncio.sleep(1)   # let the request that queued the event commit first
