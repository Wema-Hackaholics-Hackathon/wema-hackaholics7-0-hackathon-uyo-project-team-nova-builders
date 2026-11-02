"""Billing per business: plans, live usage, invoices, Bachs checkout.

PRICES ARE PLACEHOLDERS — edit PLANS below when the real ones are decided.

Rules
- Billing belongs to the organisation (the legal entity), never to a person.
- Only Live usage counts; Test usage is shown but free.
- An invoice is paid only when Bachs's signed `collection.succeeded` webhook arrives
  with its reference (inv_…) and the right amount. The browser coming back from the
  checkout page proves nothing.
- Upgrading starts a new 30-day period from the moment of payment. Choosing the free
  plan switches immediately. Paid periods renew by opening a renewal invoice when they
  end (run from the cleanup loop); unpaid renewals are not enforced yet.
"""

from __future__ import annotations

import io
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.api_errors import ApiError
from app.models import AuditLog, ConsoleUser, Invoice, Organisation, UsageEvent
from app.services.checks_service import as_utc, iso, utcnow

PERIOD = timedelta(days=30)

# code → plan. price_kobo None = custom (talk to sales). limit = billable live checks per period.
PLANS: dict[str, dict[str, Any]] = {
    "starter": {"name": "Starter", "price_kobo": 0, "limit": 500, "seats": 2,
                "features": ["500 verifications / month", "Webhooks", "2 team seats", "Email support"]},
    "growth": {"name": "Growth", "price_kobo": 150_000_00, "limit": 5_000, "seats": 3,
               "features": ["5,000 verifications / month", "Unlimited webhook events", "3 team seats", "Email support"]},
    "business": {"name": "Business", "price_kobo": 420_000_00, "limit": 15_000, "seats": 5,
                 "features": ["15,000 verifications / month", "Unlimited webhook events", "5 team seats", "Email + chat support"]},
    "enterprise": {"name": "Enterprise", "price_kobo": None, "limit": None, "seats": None,
                   "features": ["Custom volume", "Dedicated support", "SLA", "Unlimited seats"]},
}


def plan_out(code: str) -> dict[str, Any]:
    p = PLANS[code]
    return {"code": code, **p, "price_ngn": None if p["price_kobo"] is None else p["price_kobo"] // 100}


def invoice_out(i: Invoice) -> dict[str, Any]:
    return {"id": i.id, "number": i.number, "kind": i.kind, "plan": PLANS[i.plan_code]["name"], "plan_code": i.plan_code,
            "period_start": iso(i.period_start), "period_end": iso(i.period_end), "amount_ngn": i.amount_kobo // 100,
            "status": i.status, "paid_at": iso(i.paid_at), "created_at": iso(i.created_at)}


def current_period(org: Organisation, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Paid plans: the paid period. Starter: rolling 30 days."""
    now = now or utcnow()
    start, end = as_utc(org.plan_period_start), as_utc(org.plan_period_end)
    if org.plan_code != "starter" and start and end and start <= now < end:
        return start, end
    return now - PERIOD, now


async def usage(db: AsyncSession, org: Organisation) -> dict[str, Any]:
    start, end = current_period(org)
    out: dict[str, Any] = {"period_start": iso(start), "period_end": iso(end)}
    for env in ("live", "test"):
        rows = (await db.exec(select(UsageEvent.check_type, func.count()).where(
            UsageEvent.org_id == org.id, UsageEvent.env == env, UsageEvent.created_at >= start, UsageEvent.created_at < end)
            .group_by(UsageEvent.check_type))).all()
        by = {t: n for t, n in rows}
        out[env] = {"total": sum(by.values()), "by_check": by}
    limit = PLANS[org.plan_code]["limit"]
    used = out["live"]["total"]
    out["limit"] = limit
    out["projected_limit_date"] = None
    if limit and used:
        days = max((utcnow() - start).total_seconds() / 86400, 1)
        hit = start + timedelta(days=limit / (used / days))
        if hit < end:
            out["projected_limit_date"] = iso(hit)
    return out


async def _next_number(db: AsyncSession) -> str:
    year = utcnow().year
    n = (await db.exec(select(func.count()).select_from(Invoice).where(col(Invoice.number).startswith(f"INV-{year}-")))).one()
    return f"INV-{year}-{n + 1:04d}"


async def start_checkout(db: AsyncSession, org: Organisation, member: ConsoleUser, plan_code: str,
                         return_url: str) -> dict[str, Any]:
    """Change plan. Free plan → immediate. Paid → open invoice + Bachs checkout URL."""
    if plan_code not in PLANS:
        raise ApiError(422, "unknown_plan", f"Unknown plan '{plan_code}'", "plan_code")
    plan = PLANS[plan_code]
    if plan["price_kobo"] is None:
        raise ApiError(422, "contact_sales", "Enterprise is arranged with our team — email sales@foid.ng")
    if plan_code == org.plan_code:
        raise ApiError(409, "same_plan", "You're already on this plan")
    if plan["price_kobo"] == 0:
        org.plan_code, org.plan_period_start, org.plan_period_end = plan_code, None, None
        db.add(org)
        db.add(AuditLog(org_id=org.id, actor_type="member", actor_id=member.id, action="billing.plan_changed",
                        meta={"plan": plan_code}))
        await db.commit()
        return {"plan": plan_out(plan_code), "checkout_url": None, "invoice": None}

    for old in (await db.exec(select(Invoice).where(Invoice.org_id == org.id, Invoice.kind == "plan_change",
                                                    Invoice.status == "open"))).all():
        old.status = "void"     # only one pending plan change at a time
        db.add(old)
    now = utcnow()
    inv = Invoice(org_id=org.id, number=await _next_number(db), kind="plan_change", plan_code=plan_code,
                  period_start=now, period_end=now + PERIOD, amount_kobo=plan["price_kobo"], created_by=member.id)
    db.add(inv)
    await db.flush()
    url = await _bachs_checkout(db, org, member, inv, return_url)
    await db.commit()
    return {"plan": plan_out(plan_code), "checkout_url": url, "invoice": invoice_out(inv)}


async def pay_invoice(db: AsyncSession, org: Organisation, member: ConsoleUser, inv: Invoice, return_url: str) -> str:
    if inv.status != "open":
        raise ApiError(409, "invoice_not_open", f"This invoice is {inv.status}")
    url = await _bachs_checkout(db, org, member, inv, return_url)
    await db.commit()
    return url


async def _bachs_checkout(db: AsyncSession, org: Organisation, member: ConsoleUser, inv: Invoice, return_url: str) -> str:
    from app.services import bachs_service
    if not get_settings().BACHS_API_KEY:
        raise ApiError(503, "payments_not_configured", "Payments aren't set up on this server (BACHS_API_KEY is empty)")
    inv.bachs_reference = "inv_" + secrets.token_hex(12)       # new reference per attempt
    sep = "&" if "?" in return_url else "?"
    try:
        result: Any = await bachs_service.create_checkout_session(
            amount_ngn=inv.amount_kobo // 100, email=org.support_email or member.email,
            name=org.name, reference=inv.bachs_reference,
            success_url=f"{return_url}{sep}invoice={inv.id}", cancel_url=f"{return_url}{sep}cancelled={inv.id}",
            metadata={"org_id": org.id, "invoice_id": inv.id, "number": inv.number},
        )
    except Exception as exc:
        raise ApiError(502, "payment_provider_error", f"Couldn't start the Bachs checkout: {exc}") from exc
    inv.checkout_url = str(result.get("checkout_url") or "")
    db.add(inv)
    return inv.checkout_url


async def confirm_payment(db: AsyncSession, reference: str, data: dict[str, Any]) -> str:
    """Called by the Bachs webhook for inv_… references. Idempotent. Returns a short status."""
    inv = (await db.exec(select(Invoice).where(Invoice.bachs_reference == reference))).first()
    if inv is None:
        return "invoice_not_found"
    if inv.status == "paid":
        return "already_paid"
    amount = data.get("amount")
    if amount is not None and round(float(amount) * 100) != inv.amount_kobo:
        print(f"[billing] amount mismatch for {inv.number}: got {amount}, expected {inv.amount_kobo / 100}", flush=True)
        return "amount_mismatch"
    org = await db.get(Organisation, inv.org_id)
    assert org is not None
    now = utcnow()
    if inv.kind == "plan_change":       # the new period starts when the money arrives
        inv.period_start, inv.period_end = now, now + PERIOD
    inv.status, inv.paid_at = "paid", now
    org.plan_code, org.plan_period_start, org.plan_period_end = inv.plan_code, inv.period_start, inv.period_end
    if inv.kind == "plan_change":
        for other in (await db.exec(select(Invoice).where(Invoice.org_id == org.id, Invoice.kind == "renewal",
                                                          Invoice.status == "open"))).all():
            other.status = "void"       # superseded by the new period
            db.add(other)
    db.add(inv)
    db.add(org)
    db.add(AuditLog(org_id=org.id, actor_type="system", actor_id=None, action="billing.paid",
                    target_type="invoice", target_id=inv.id, meta={"number": inv.number, "plan": inv.plan_code}))
    from app.services.console_inbox import notify
    await notify(db, org.id, "invoice_paid", f"Payment received — {inv.number}",
                 f"You're on the {PLANS[inv.plan_code]['name']} plan until {inv.period_end:%d %b %Y}.", link="/billing", min_role="admin")
    await db.commit()
    return "ok"


async def open_renewals(db: AsyncSession, now: datetime | None = None) -> int:
    """For paid plans whose period ended, open one renewal invoice for the next period."""
    now = now or utcnow()
    made = 0
    for org in (await db.exec(select(Organisation).where(Organisation.plan_code != "starter",
                                                         col(Organisation.plan_period_end) <= now))).all():
        price = PLANS[org.plan_code]["price_kobo"]
        end = as_utc(org.plan_period_end)
        if not price or end is None:
            continue
        exists = (await db.exec(select(Invoice.id).where(Invoice.org_id == org.id, Invoice.kind == "renewal",
                                                         Invoice.period_start == end))).first()
        if exists:
            continue
        number = await _next_number(db)
        db.add(Invoice(org_id=org.id, number=number, kind="renewal", plan_code=org.plan_code,
                       period_start=end, period_end=end + PERIOD, amount_kobo=price))
        from app.services.console_inbox import notify
        await notify(db, org.id, "invoice_due", f"Renewal invoice {number} is due",
                     f"₦{price // 100:,} for the {PLANS[org.plan_code]['name']} plan.", link="/billing", min_role="admin")
        await db.flush()
        made += 1
    await db.commit()
    return made


def invoice_pdf(org: Organisation, inv: Invoice) -> bytes:
    from fpdf import FPDF
    from app.utils.pdf_utils import draw_foid_header

    pdf = FPDF()
    pdf.add_page()
    y = draw_foid_header(pdf, "Invoice", inv.number) + 12
    pdf.set_xy(10, y)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, f"Billed to: {org.name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for line in (org.registered_address, org.support_email, f"RC {org.rc_number}" if org.rc_number else None):
        if line:
            pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    start, end = as_utc(inv.period_start), as_utc(inv.period_end)
    rows = [("Invoice", inv.number), ("Status", inv.status.upper()),
            ("Plan", f"{PLANS[inv.plan_code]['name']} ({'renewal' if inv.kind == 'renewal' else 'plan change'})"),
            ("Period", f"{start:%d %b %Y} - {end:%d %b %Y}" if start and end else "-"),
            ("Issued", f"{as_utc(inv.created_at):%d %b %Y}"),
            ("Paid", f"{as_utc(inv.paid_at):%d %b %Y %H:%M} UTC" if inv.paid_at else "-")]
    for k, v in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 7, k)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, v, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"Total: NGN {inv.amount_kobo / 100:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "Payments are processed by Bachs. Questions: billing@foid.ng", new_x="LMARGIN", new_y="NEXT")
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
