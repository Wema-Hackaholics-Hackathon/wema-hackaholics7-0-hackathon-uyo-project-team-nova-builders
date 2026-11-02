"""Billing — /api/v1/business/... (per organisation; owner/admin)

GET  /plans                                         placeholder plans (services/billing_service.PLANS)
GET  /organisations/{id}/billing                    plan, period, live/test usage, limit projection, invoices
POST /organisations/{id}/billing/checkout           {plan_code} → free: switched; paid: invoice + Bachs checkout_url
POST /organisations/{id}/invoices/{inv}/pay         new Bachs checkout for an open invoice
GET  /organisations/{id}/invoices/{inv}             one invoice (the console polls this after checkout)
GET  /organisations/{id}/invoices/{inv}/pdf         PDF

Payment confirmation arrives through the Bachs webhook (routers/wallet.py dispatches inv_… references here).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db, get_settings
from app.core.api_errors import ApiError
from app.core.dependencies import require_verified_console_user
from app.models import ConsoleUser, Invoice, Organisation
from app.routers.business import _member  # pyright: ignore[reportPrivateUsage]
from app.services import billing_service as billing

router = APIRouter(prefix="/business", tags=["business-billing"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]


class CheckoutBody(BaseModel):
    plan_code: str


def _return_url() -> str:
    return get_settings().CONSOLE_URL.rstrip("/") + "/billing"


async def _org(db: AsyncSession, org_id: str, user: ConsoleUser) -> Organisation:
    await _member(db, org_id, user, "admin")
    org = await db.get(Organisation, org_id)
    assert org is not None
    return org


async def _invoice(db: AsyncSession, org_id: str, invoice_id: str) -> Invoice:
    inv = await db.get(Invoice, invoice_id)
    if inv is None or inv.org_id != org_id:
        raise ApiError(404, "invoice_not_found", "No such invoice")
    return inv


@router.get("/plans")
async def plans(_user: CurrentUser) -> list[dict[str, Any]]:
    return [billing.plan_out(c) for c in billing.PLANS]


@router.get("/organisations/{org_id}/billing")
async def get_billing(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    org = await _org(db, org_id, user)
    invoices = (await db.exec(select(Invoice).where(Invoice.org_id == org_id, Invoice.status != "void")
                              .order_by(col(Invoice.created_at).desc()))).all()
    return {"plan": billing.plan_out(org.plan_code), "usage": await billing.usage(db, org),
            "invoices": [billing.invoice_out(i) for i in invoices]}


@router.post("/organisations/{org_id}/billing/checkout")
async def checkout(org_id: str, body: CheckoutBody, user: CurrentUser, db: Db) -> dict[str, Any]:
    org = await _org(db, org_id, user)
    return await billing.start_checkout(db, org, user, body.plan_code, _return_url())


@router.post("/organisations/{org_id}/invoices/{invoice_id}/pay")
async def pay(org_id: str, invoice_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    org = await _org(db, org_id, user)
    inv = await _invoice(db, org_id, invoice_id)
    return {"checkout_url": await billing.pay_invoice(db, org, user, inv, _return_url()), "invoice": billing.invoice_out(inv)}


@router.get("/organisations/{org_id}/invoices/{invoice_id}")
async def get_invoice(org_id: str, invoice_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _org(db, org_id, user)
    return billing.invoice_out(await _invoice(db, org_id, invoice_id))


@router.get("/organisations/{org_id}/invoices/{invoice_id}/pdf")
async def invoice_pdf(org_id: str, invoice_id: str, user: CurrentUser, db: Db) -> Response:
    org = await _org(db, org_id, user)
    inv = await _invoice(db, org_id, invoice_id)
    return Response(billing.invoice_pdf(org, inv), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"', "Cache-Control": "no-store"})
