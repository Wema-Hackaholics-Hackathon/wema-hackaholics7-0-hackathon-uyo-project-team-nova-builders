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
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db
from ..core.dependencies import get_current_user
from ..models.ledger_entry import LedgerEntry
from ..models.user import User

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

    # Title band
    pdf.set_fill_color(22, 163, 74)
    pdf.rect(0, 0, 297, 22, "F")
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(12, 5)
    pdf.cell(0, 10, "FOID - Reports & Insights", ln=False)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(12, 14)
    pdf.cell(0, 6, f"Generated {now.strftime('%d %b %Y %H:%M UTC')}  |  {current_user.first_name} {current_user.last_name}")
    pdf.set_text_color(30, 30, 30)
    pdf.set_y(30)

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
        pdf.set_fill_color(243, 244, 246)
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
        pdf.set_fill_color(22, 163, 74)
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
    pdf.cell(0, 6, "FOID - Identity & Digital Risk Assessment | This report is system-generated", align="C")

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
    """Generate a detailed audit PDF for a single calendar month."""
    from fpdf import FPDF

    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="month must be YYYY-MM")

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
    # Filter to exact month (next-month boundary)
    entries = [
        e for e in all_entries
        if e.entry_date.year == year and e.entry_date.month == mon
    ]

    income_entries  = [e for e in entries if e.entry_type == "income"]
    expense_entries = [e for e in entries if e.entry_type == "expense"]
    total_income    = sum(float(e.amount) for e in income_entries)
    total_expense   = sum(float(e.amount) for e in expense_entries)
    net             = total_income - total_expense
    est_tax         = max(0.0, round(net * 0.075, 2))

    month_label = date(year, mon, 1).strftime("%B %Y")
    now         = datetime.now(timezone.utc)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Title band
    pdf.set_fill_color(22, 163, 74)
    pdf.rect(0, 0, 210, 24, "F")
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(14, 5)
    pdf.cell(0, 10, f"FOID - Monthly Audit: {month_label}", ln=False)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(14, 15)
    pdf.cell(0, 6, f"Generated {now.strftime('%d %b %Y %H:%M UTC')}  |  {current_user.first_name} {current_user.last_name}")
    pdf.set_text_color(30, 30, 30)
    pdf.set_y(32)

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
    pdf.set_fill_color(243, 244, 246)
    pdf.cell(0, 7, "  Summary", fill=True, ln=True)
    pdf.ln(1)
    kv("Total Income",    f"N{total_income:,.2f}", (22, 163, 74))
    kv("Total Expenses",  f"N{total_expense:,.2f}", (220, 38, 38) if total_expense > 0 else (30, 30, 30))
    kv("Net Profit",      f"N{net:,.2f}", (22, 163, 74) if net >= 0 else (220, 38, 38))
    kv("Estimated Tax",   f"N{est_tax:,.2f} (7.5%)")
    kv("Total entries",   str(len(entries)))
    pdf.ln(4)

    # Entry table helper
    def entry_table(title: str, rows: list[LedgerEntry]) -> None:
        if not rows:
            return
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(243, 244, 246)
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

    entry_table("Income Entries", income_entries)
    entry_table("Expense Entries", expense_entries)

    # Category breakdown
    if expense_entries:
        cat_map: dict[str, float] = {}
        for e in expense_entries:
            cat_map[e.category] = cat_map.get(e.category, 0.0) + float(e.amount)
        sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(243, 244, 246)
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
    pdf.cell(0, 6, "FOID - Identity & Digital Risk Assessment | This report is system-generated", align="C")

    filename = f"foid_audit_{month}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
