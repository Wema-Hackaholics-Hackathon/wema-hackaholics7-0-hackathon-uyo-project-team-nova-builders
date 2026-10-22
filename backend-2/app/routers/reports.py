"""Reports & Insights router.

Endpoints:
  GET  /reports/summary          — monthly breakdown (income, expense, net, tax) for all months
  GET  /reports/export/csv       — full ledger as CSV (same shape as ledger export)
  GET  /reports/export/pdf       — full summary report PDF
  GET  /reports/monthly-pdf      — single-month audit PDF (?month=YYYY-MM)
"""

from __future__ import annotations

import csv
import io

from ..utils.pdf_utils import draw_foid_header
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db
from ..core.dependencies import get_current_user
from ..models.connected_bank import ConnectedBank
from ..models.ledger_entry import LedgerEntry
from ..models.user import User
from ..services import mono_service

router = APIRouter(prefix="/reports", tags=["reports"])

TAX_RATE = Decimal("0.075")


def _month_label(d: date) -> str:
    return d.strftime("%b %Y")


# ---------------------------------------------------------------------------
# GET /reports/summary
# ---------------------------------------------------------------------------

@router.get("/summary")
async def reports_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return monthly aggregated income, expense, net profit, estimated tax."""
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.user_id == current_user.id)
        .order_by(col(LedgerEntry.entry_date).asc())
    )
    result = await db.exec(stmt)
    entries = result.all()

    # Group by YYYY-MM
    monthly: dict[str, dict] = {}
    for e in entries:
        key = e.entry_date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {
                "month": _month_label(e.entry_date),
                "year_month": key,
                "income": Decimal("0"),
                "expense": Decimal("0"),
            }
        if e.entry_type == "income":
            monthly[key]["income"] += e.amount
        else:
            monthly[key]["expense"] += e.amount

    rows = []
    for m in sorted(monthly.keys(), reverse=True):
        d = monthly[m]
        income  = float(d["income"])
        expense = float(d["expense"])
        net     = income - expense
        tax     = max(0.0, round(net * float(TAX_RATE), 2))
        rows.append({
            "month":      d["month"],
            "year_month": m,
            "income":     income,
            "expense":    expense,
            "net":        net,
            "tax":        tax,
        })
    return rows


# ---------------------------------------------------------------------------
# GET /reports/export/csv
# ---------------------------------------------------------------------------

@router.get("/export/csv")
async def export_csv(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download monthly summary as CSV."""
    rows = await reports_summary(current_user=current_user, db=db)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Month", "Income (N)", "Expenses (N)", "Net Profit (N)", "Est. Tax (N)"])
    for r in rows:
        writer.writerow([r["month"], r["income"], r["expense"], r["net"], r["tax"]])

    buf.seek(0)
    filename = f"foid_report_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /reports/export/pdf  — full report PDF
# ---------------------------------------------------------------------------

@router.get("/export/pdf")
async def export_pdf(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download a full summary report PDF covering all months."""
    from fpdf import FPDF

    rows = await reports_summary(current_user=current_user, db=db)
    now  = datetime.now(timezone.utc)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    # Title band — FOID purple
    band_h = draw_foid_header(
        pdf,
        title="Reports & Insights",
        subtitle=f"Generated {now.strftime('%d %b %Y %H:%M UTC')}  |  {current_user.first_name} {current_user.last_name}",
        landscape=True,
    )
    pdf.set_text_color(30, 30, 30)
    pdf.set_y(band_h + 6)

    if not rows:
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 10, "No ledger data found.", ln=True)
    else:
        cols: list[tuple[str, int]] = [
            ("Month",          40),
            ("Income (N)",     48),
            ("Expenses (N)",   48),
            ("Net Profit (N)", 48),
            ("Est. Tax (N)",   48),
        ]
        # Header
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(245, 240, 255)
        pdf.set_text_color(80, 80, 80)
        for label, w in cols:
            pdf.cell(w, 8, label, border="B", fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        for i, r in enumerate(rows):
            fill = i % 2 == 0
            pdf.set_fill_color(247, 248, 250) if fill else pdf.set_fill_color(255, 255, 255)
            net_color = (22, 163, 74) if r["net"] >= 0 else (220, 38, 38)
            for (_, w), val in zip(cols, [
                r["month"],
                f"N{r['income']:,.2f}",
                f"N{r['expense']:,.2f}",
                f"N{r['net']:,.2f}",
                f"N{r['tax']:,.2f}",
            ]):
                if val.startswith("N") and "-" in val:
                    pdf.set_text_color(*net_color)
                pdf.cell(w, 7, val, border=0, fill=fill, align="R" if val != r["month"] else "L")
                pdf.set_text_color(30, 30, 30)
            pdf.ln()

        # Totals row
        total_income  = sum(r["income"]  for r in rows)
        total_expense = sum(r["expense"] for r in rows)
        total_net     = sum(r["net"]     for r in rows)
        total_tax     = sum(r["tax"]     for r in rows)
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(200, 0, 222)
        pdf.set_text_color(255, 255, 255)
        for (_, w), val in zip(cols, [
            "TOTAL",
            f"N{total_income:,.2f}",
            f"N{total_expense:,.2f}",
            f"N{total_net:,.2f}",
            f"N{total_tax:,.2f}",
        ]):
            pdf.cell(w, 8, val, fill=True, align="R" if val != "TOTAL" else "L")
        pdf.ln()

    pdf.set_y(-16)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, "FOID — Identity & Financial Trust Platform | This report is system-generated", align="C")

    filename = f"foid_report_{date.today().isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /reports/monthly-pdf  — single-month audit PDF
# ---------------------------------------------------------------------------

@router.get("/monthly-pdf")
async def monthly_pdf(
    month: str = Query(description="Month in YYYY-MM format, e.g. 2025-07"),
    current_user: Annotated[User, Depends(get_current_user)] = None,  # type: ignore[assignment]  # noqa: B008
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Generate a detailed audit PDF for a single calendar month.

    Pulls data from two sources and merges them:
      1. LedgerEntry rows (manually added or receipt-scanned)
      2. Mono Open Banking transactions for that month across all connected banks
    """
    from fpdf import FPDF
    import httpx

    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="month must be YYYY-MM")

    # ── 1. Ledger entries for this month ──────────────────────────────
    stmt = (
        select(LedgerEntry)
        .where(
            LedgerEntry.user_id == current_user.id,
            col(LedgerEntry.entry_date) >= date(year, mon, 1),
        )
        .order_by(col(LedgerEntry.entry_date).asc())
    )
    result = await db.exec(stmt)
    all_entries = result.all()
    entries = [
        e for e in all_entries
        if e.entry_date.year == year and e.entry_date.month == mon
    ]

    income_entries  = [e for e in entries if e.entry_type == "income"]
    expense_entries = [e for e in entries if e.entry_type == "expense"]
    ledger_income   = sum(float(e.amount) for e in income_entries)
    ledger_expense  = sum(float(e.amount) for e in expense_entries)

    # ── 2. Mono transactions for this month ───────────────────────────
    start_str = f"{year}-{mon:02d}-01"
    # last day of month
    if mon == 12:
        end_str = f"{year}-12-31"
    else:
        from datetime import timedelta as _timedelta
        end_str = (date(year, mon + 1, 1) - _timedelta(days=1)).strftime("%Y-%m-%d")

    banks_result = await db.exec(
        select(ConnectedBank).where(ConnectedBank.user_id == current_user.id)
    )
    connected_banks = banks_result.all()

    mono_income: float = 0.0
    mono_expense: float = 0.0
    mono_tx_rows: list[dict[str, Any]] = []   # for the PDF transaction table

    for bank in connected_banks:
        try:
            data: Any = await mono_service.get_transactions(
                bank.mono_account_id,
                start=start_str,
                end=end_str,
                limit=500,
            )
            for tx in data.get("data", []):
                amount_naira = tx.get("amount", 0) / 100   # kobo → naira
                tx_type = tx.get("type", "")
                tx_date_str = tx.get("date", "")[:10]
                narration = tx.get("narration", "")[:60]
                category = tx.get("category") or "Other"
                if tx_type == "credit":
                    mono_income += amount_naira
                else:
                    mono_expense += amount_naira
                mono_tx_rows.append({
                    "date": tx_date_str,
                    "narration": narration,
                    "category": category,
                    "type": tx_type,
                    "amount": amount_naira,
                    "bank": bank.name,
                })
        except (httpx.HTTPStatusError, httpx.TimeoutException, Exception):
            # If one bank fails, continue with others
            continue

    # ── Merged totals ─────────────────────────────────────────────────
    total_income  = ledger_income + mono_income
    total_expense = ledger_expense + mono_expense
    net           = total_income - total_expense
    est_tax       = max(0.0, round(net * 0.075, 2))

    month_label = date(year, mon, 1).strftime("%B %Y")
    now         = datetime.now(timezone.utc)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Title band — FOID purple
    band_h = draw_foid_header(
        pdf,
        title=f"Monthly Audit: {month_label}",
        subtitle=f"Generated {now.strftime('%d %b %Y %H:%M UTC')}  |  {current_user.first_name} {current_user.last_name}",
    )
    pdf.set_text_color(30, 30, 30)
    pdf.set_y(band_h + 8)

    # Summary box
    def kv(label: str, val: str, color: tuple[int, int, int] = (30, 30, 30)) -> None:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(52, 7, label)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*color)
        pdf.cell(0, 7, val, ln=True)
        pdf.set_text_color(30, 30, 30)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(245, 240, 255)
    pdf.cell(0, 7, "  Summary", fill=True, ln=True)
    pdf.ln(1)
    kv("Total Income",    f"N{total_income:,.2f}", (22, 163, 74))
    kv("Total Expenses",  f"N{total_expense:,.2f}", (220, 38, 38) if total_expense > 0 else (30, 30, 30))
    kv("Net Profit",      f"N{net:,.2f}", (22, 163, 74) if net >= 0 else (220, 38, 38))
    kv("Estimated Tax",   f"N{est_tax:,.2f} (7.5%)")
    kv("Sources",         f"Ledger: {len(entries)} entries   |   Mono: {len(mono_tx_rows)} bank transactions")
    pdf.ln(4)

    # ── Ledger entry table helper ──────────────────────────────────────
    def entry_table(title: str, rows: list[LedgerEntry]) -> None:
        if not rows:
            return
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(245, 240, 255)
        pdf.cell(0, 7, f"  {title}", fill=True, ln=True)
        pdf.ln(1)

        tcols: list[tuple[str, int]] = [
            ("Date",        24),
            ("Description", 80),
            ("Category",    30),
            ("Amount (N)",  38),
        ]
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(80, 80, 80)
        for lbl, w in tcols:
            pdf.cell(w, 6, lbl, border="B")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(30, 30, 30)
        for i, e in enumerate(rows):
            fill = i % 2 == 0
            pdf.set_fill_color(247, 248, 250) if fill else pdf.set_fill_color(255, 255, 255)
            desc = e.description[:48] + ("..." if len(e.description) > 48 else "")
            for (_, w), val in zip(tcols, [
                str(e.entry_date),
                desc,
                e.category,
                f"N{float(e.amount):,.2f}",
            ]):
                pdf.cell(w, 6, val, fill=fill)
            pdf.ln()
        pdf.ln(4)

    entry_table("Ledger Income Entries", income_entries)
    entry_table("Ledger Expense Entries", expense_entries)

    # ── Mono Open Banking transactions for this month ──────────────────
    if mono_tx_rows:
        mono_tx_rows.sort(key=lambda r: r["date"])
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(245, 240, 255)
        pdf.cell(0, 7, f"  Open Banking Transactions ({len(mono_tx_rows)} via Mono)", fill=True, ln=True)
        pdf.ln(1)

        mtcols: list[tuple[str, int]] = [
            ("Date",        22),
            ("Bank",        28),
            ("Narration",   78),
            ("Category",    26),
            ("Type",        16),
            ("Amount (N)",  36),
        ]
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(80, 80, 80)
        for lbl, w in mtcols:
            pdf.cell(w, 6, lbl, border="B")
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(30, 30, 30)
        for i, tx in enumerate(mono_tx_rows):
            fill = i % 2 == 0
            pdf.set_fill_color(247, 248, 250) if fill else pdf.set_fill_color(255, 255, 255)
            # colour the amount by type
            for (_, w), val in zip(mtcols, [
                tx["date"],
                tx["bank"][:12],
                tx["narration"][:50],
                tx["category"][:14],
                tx["type"],
                f"N{tx['amount']:,.2f}",
            ]):
                pdf.cell(w, 5, val, fill=fill)
            pdf.ln()
        pdf.ln(4)

    # ── Combined category breakdown ────────────────────────────────────
    # Merge ledger expenses + Mono debits
    cat_map: dict[str, float] = {}
    for e in expense_entries:
        cat_map[e.category] = cat_map.get(e.category, 0.0) + float(e.amount)
    for tx in mono_tx_rows:
        if tx["type"] == "debit":
            cat = tx["category"] or "Other"
            cat_map[cat] = cat_map.get(cat, 0.0) + tx["amount"]

    if cat_map:
        sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(245, 240, 255)
        pdf.cell(0, 7, "  Expense Breakdown by Category", fill=True, ln=True)
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)
        for cat, amt in sorted_cats:
            pct = (amt / total_expense * 100) if total_expense > 0 else 0
            pdf.set_text_color(107, 114, 128)
            pdf.cell(52, 6, cat)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 6, f"N{amt:,.2f}  ({pct:.1f}%)", ln=True)
        pdf.ln(4)

    # Footer
    pdf.set_y(-16)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, "FOID — Identity & Financial Trust Platform | This report is system-generated", align="C")

    filename = f"foid_audit_{month}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
