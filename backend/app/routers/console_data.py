"""Console data — /api/v1/business/organisations/{org_id}/...

GET request-logs          ?env&status_class=2|4|5&q&limit&offset   Open API calls (30 days kept)
GET request-stats         ?env&days=30                             daily successful/failed + totals, for the chart
GET activity              ?env&limit=10                            verifications + webhook deliveries + team actions
GET search                ?env&q                                   top-bar search: people and request IDs
GET users/export          ?env&status&q                            CSV (reviewer+; same consent rules as the table)
GET request-logs/export   ?env&status_class&q                      CSV
GET notifications         ?limit                                   the member's own bell items + unread count
POST notifications/read-all, notifications/{id}/read
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.dependencies import require_verified_console_user
from app.models import ApiRequestLog, AuditLog, ConsoleNotification, ConsoleUser, Verification, WebhookDelivery, WebhookEndpoint
from app.routers.business import _member  # pyright: ignore[reportPrivateUsage]
from app.services import console_inbox as inbox
from app.services import console_views as cv
from app.services import request_log_service as rl
from app.services.checks_service import as_utc, iso, utcnow

router = APIRouter(prefix="/business", tags=["business-console"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]
Env = Literal["test", "live"]
StatusClass = Literal["2", "4", "5"]


# ── request logs ────────────────────────────────────────────────────────────

def _log_query(org_id: str, env: str, status_class: str | None, q: str | None) -> SelectOfScalar[ApiRequestLog]:
    query = select(ApiRequestLog).where(ApiRequestLog.org_id == org_id, ApiRequestLog.env == env)
    if status_class:
        lo = int(status_class) * 100
        query = query.where(ApiRequestLog.status >= lo, ApiRequestLog.status < lo + 100)
    if q and q.strip():
        term = q.strip()
        query = query.where(col(ApiRequestLog.request_id).startswith(term) | col(ApiRequestLog.path).contains(term))
    return query


@router.get("/organisations/{org_id}/request-logs")
async def request_logs(org_id: str, user: CurrentUser, db: Db, env: Env = "test", status_class: StatusClass | None = None,
                       q: str | None = None, limit: int = 25, offset: int = 0) -> dict[str, Any]:
    await _member(db, org_id, user)
    query = _log_query(org_id, env, status_class, q)
    total = (await db.exec(select(func.count()).select_from(query.subquery()))).one()
    limit = max(1, min(limit, 100))
    rows = (await db.exec(query.order_by(col(ApiRequestLog.created_at).desc()).offset(offset).limit(limit))).all()
    return {"data": [rl.log_out(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/organisations/{org_id}/request-stats")
async def request_stats(org_id: str, user: CurrentUser, db: Db, env: Env = "test",
                        days: Annotated[int, Query(ge=1, le=90)] = 30) -> dict[str, Any]:
    """Successful = status below 400. `previous_total` is the same-length period before, for a trend."""
    await _member(db, org_id, user)
    now = utcnow()
    since, before = now - timedelta(days=days), now - timedelta(days=2 * days)
    rows = (await db.exec(select(ApiRequestLog.created_at, ApiRequestLog.status, ApiRequestLog.latency_ms).where(
        ApiRequestLog.org_id == org_id, ApiRequestLog.env == env, ApiRequestLog.created_at >= before))).all()
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = failed = previous = latency = 0
    for created, status, ms in rows:
        t = as_utc(created) or now
        if t < since:
            previous += 1
            continue
        total += 1
        latency += ms
        ok = status < 400
        failed += 0 if ok else 1
        per[t.date().isoformat()][0 if ok else 1] += 1
    start = now.date() - timedelta(days=days - 1)
    series = [{"day": d, "successful": per[d][0], "failed": per[d][1]}
              for d in ((start + timedelta(days=i)).isoformat() for i in range(days))]
    return {"env": env, "days": days, "total": total, "failed": failed, "previous_total": previous,
            "avg_latency_ms": round(latency / total) if total else None, "series": series}


# ── activity feed ───────────────────────────────────────────────────────────

_TEAM_ACTIONS = {
    "api_key.created": "API key created", "api_key.rotated": "API key regenerated", "api_key.revoked": "API key revoked",
    "webhook.created": "Webhook endpoint added", "webhook.secret_rolled": "Webhook secret rotated",
    "member.added": "Team member added", "member.role_changed": "Team role changed", "member.removed": "Team member removed",
    "organisation.updated": "Organisation details updated", "kyb.submitted": "Documents submitted for go-live",
    "kyb.approved": "Approved for Live", "kyb.rejected": "Go-live review: changes needed",
}


@router.get("/organisations/{org_id}/activity")
async def activity(org_id: str, user: CurrentUser, db: Db, env: Env = "test",
                   limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[dict[str, Any]]:
    await _member(db, org_id, user)
    items: list[dict[str, Any]] = []

    for v in (await db.exec(select(Verification).where(Verification.org_id == org_id, Verification.env == env)
                            .order_by(col(Verification.created_at).desc()).limit(limit))).all():
        if v.outcome == "passed":
            title, status = "Identity verified", "success"
        elif v.outcome == "failed" or v.status in ("expired", "cancelled"):
            title, status = f"Verification {v.outcome or v.status}", "failed"
        elif v.outcome == "needs_review":
            title, status = "Verification needs review", "pending"
        else:
            title, status = "Verification started", "pending"
        items.append({"kind": "verification", "title": title, "actor": cv.subject_code(v.subject_id), "status": status,
                      "at": iso(v.completed_at or v.created_at)})

    deliveries = (await db.exec(select(WebhookDelivery, WebhookEndpoint.url)
                                .join(WebhookEndpoint, col(WebhookEndpoint.id) == WebhookDelivery.endpoint_id)
                                .where(WebhookDelivery.org_id == org_id, WebhookEndpoint.env == env, WebhookDelivery.attempts > 0)
                                .order_by(col(WebhookDelivery.created_at).desc()).limit(limit))).all()
    for d, url in deliveries:
        ok = d.status == "delivered"
        items.append({"kind": "webhook", "title": "Webhook delivered" if ok else "Webhook delivery failed",
                      "actor": f"{d.event_type} → {urlparse(url).netloc}{urlparse(url).path}", "status": "success" if ok else "failed",
                      "at": iso(d.delivered_at or d.created_at)})

    audits = (await db.exec(select(AuditLog).where(AuditLog.org_id == org_id, col(AuditLog.action).in_(list(_TEAM_ACTIONS)))
                            .order_by(col(AuditLog.created_at).desc()).limit(limit))).all()
    actor_ids = {a.actor_id for a in audits if a.actor_type == "member" and a.actor_id}
    names = {u.id: f"{u.first_name} {u.last_name}" for u in (await db.exec(
        select(ConsoleUser).where(col(ConsoleUser.id).in_(actor_ids)))).all()} if actor_ids else {}
    for a in audits:
        a_env = (a.meta or {}).get("env")
        if a_env and a_env != env:
            continue
        actor = names.get(a.actor_id or "", "FOID team" if a.actor_type == "user" else "—")
        items.append({"kind": "team", "title": _TEAM_ACTIONS[a.action], "actor": actor, "status": "team", "at": iso(a.created_at)})

    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items[:limit]


# ── search ──────────────────────────────────────────────────────────────────

@router.get("/organisations/{org_id}/search")
async def search(org_id: str, user: CurrentUser, db: Db, q: str, env: Env = "test") -> dict[str, Any]:
    await _member(db, org_id, user)
    term = q.strip()
    if len(term) < 2:
        return {"users": [], "requests": []}
    people = [r.out() for r in await cv.rows(db, org_id, env) if r.matches(term)][:5]
    reqs = (await db.exec(select(ApiRequestLog).where(ApiRequestLog.org_id == org_id, ApiRequestLog.env == env,
                                                      col(ApiRequestLog.request_id).startswith(term))
                          .order_by(col(ApiRequestLog.created_at).desc()).limit(5))).all() if term.startswith("req_") else []
    return {"users": [{k: p[k] for k in ("id", "code", "name", "email", "status")} for p in people],
            "requests": [rl.log_out(r) for r in reqs]}


# ── CSV exports ─────────────────────────────────────────────────────────────

def _cell(v: Any) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s   # no spreadsheet formulas


def _csv(filename: str, header: list[str], rows: list[list[Any]]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows([[_cell(c) for c in r] for r in rows])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/organisations/{org_id}/users/export")
async def export_users(org_id: str, user: CurrentUser, db: Db, env: Env = "test", status: str | None = None,
                       q: str | None = None) -> Response:
    await _member(db, org_id, user, "reviewer")
    rows = [r.out() for r in await cv.rows(db, org_id, env) if (not status or r.status == status) and (not q or r.matches(q))]
    return _csv(f"foid-users-{env}-{utcnow():%Y%m%d}.csv",
                ["FOID code", "Your reference", "Name", "Email", "Checks", "Status", "FOID account", "Verified at", "Added at"],
                [[r["code"], r["customer_ref"], r["name"], r["email"], " ".join(r["checks"]), r["status"],
                  "yes" if r["has_foid_account"] else "no", r["verified_at"], r["created_at"]] for r in rows])


@router.get("/organisations/{org_id}/request-logs/export")
async def export_logs(org_id: str, user: CurrentUser, db: Db, env: Env = "test", status_class: StatusClass | None = None,
                      q: str | None = None) -> Response:
    await _member(db, org_id, user)
    rows = (await db.exec(_log_query(org_id, env, status_class, q).order_by(col(ApiRequestLog.created_at).desc())
                          .limit(10_000))).all()
    return _csv(f"foid-request-logs-{env}-{utcnow():%Y%m%d}.csv",
                ["Request ID", "Time", "Method", "Endpoint", "Status", "Latency (ms)", "Key"],
                [[r.request_id, iso(r.created_at), r.method, r.path, r.status, r.latency_ms, r.key_hint] for r in rows])


# ── notification bell ───────────────────────────────────────────────────────

@router.get("/organisations/{org_id}/notifications")
async def notifications(org_id: str, user: CurrentUser, db: Db,
                        limit: Annotated[int, Query(ge=1, le=50)] = 15) -> dict[str, Any]:
    """The signed-in member's own notifications for this business, newest first, plus the unread count."""
    await _member(db, org_id, user, allow_deactivated=True)
    mine = select(ConsoleNotification).where(ConsoleNotification.org_id == org_id, ConsoleNotification.console_user_id == user.id)
    rows = (await db.exec(mine.order_by(col(ConsoleNotification.created_at).desc()).limit(limit))).all()
    unread = (await db.exec(select(func.count()).select_from(
        mine.where(col(ConsoleNotification.read_at).is_(None)).subquery()))).one()
    return {"data": [inbox.out(n) for n in rows], "unread": unread}


@router.post("/organisations/{org_id}/notifications/read-all", status_code=204)
async def notifications_read_all(org_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, allow_deactivated=True)
    now = utcnow()
    for n in (await db.exec(select(ConsoleNotification).where(
            ConsoleNotification.org_id == org_id, ConsoleNotification.console_user_id == user.id,
            col(ConsoleNotification.read_at).is_(None)))).all():
        n.read_at = now
        db.add(n)
    await db.commit()


@router.post("/organisations/{org_id}/notifications/{notification_id}/read", status_code=204)
async def notification_read(org_id: str, notification_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, allow_deactivated=True)
    n = await db.get(ConsoleNotification, notification_id)
    if n is None or n.org_id != org_id or n.console_user_id != user.id:   # only your own
        raise ApiError(404, "notification_not_found", "No such notification")
    if n.read_at is None:
        n.read_at = utcnow()
        db.add(n)
        await db.commit()
