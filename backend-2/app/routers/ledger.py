"""AI Business Ledger router.

Endpoints:
  POST   /ledger/upload        — upload receipt, OCR via Groq, costs 4 credits
  POST   /ledger/chat          — AI spending-summary chat, costs 1 credit
  GET    /ledger               — paginated list of ledger entries
  GET    /ledger/export/csv    — download all entries as CSV
  GET    /ledger/export/pdf    — download all entries as PDF
  PATCH  /ledger/{id}          — edit description / category / amount
"""

from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..config import get_db, get_settings
from ..core.dependencies import get_current_user, require_verified_email
from ..models.ledger_entry import LedgerEntry
from ..models.user import User
from ..models.wallet import Wallet
from ..schemas.ledger import ChatRequest, ChatResponse, LedgerEntryCreate, LedgerEntryOut, LedgerEntryUpdate
from ..services import groq_service, wallet_service

router = APIRouter(prefix="/ledger", tags=["ledger"])

_UPLOAD_DIR = Path("uploads")
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_SCAN_COST = 4   # credits per receipt scan
_CHAT_COST = 1   # credits per chat message


def _ensure_upload_dir() -> None:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _get_wallet(user_id: str, db: AsyncSession) -> Wallet:
    from sqlmodel import select as sqlsel
    result = await db.exec(sqlsel(Wallet).where(Wallet.user_id == user_id))
    wallet = result.first()
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return wallet


@router.post("/upload", response_model=LedgerEntryOut, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    file: Annotated[UploadFile, File(description="Receipt image or PDF, max 10 MB")],
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> LedgerEntryOut:
    """Upload a receipt, run Groq OCR, persist a LedgerEntry, deduct 4 credits."""
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WebP, PDF",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large — maximum 10 MB",
        )

    # Check balance before expensive Groq call
    wallet = await _get_wallet(current_user.id, db)
    if wallet.balance < _SCAN_COST:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {_SCAN_COST}, have {wallet.balance}",
        )

    # Save file to disk
    _ensure_upload_dir()
    ext = Path(file.filename or "upload").suffix or ".bin"
    filename = f"{uuid.uuid4()}{ext}"
    file_path = _UPLOAD_DIR / filename
    file_path.write_bytes(file_bytes)

    # Run Groq OCR
    try:
        parsed = await groq_service.parse_receipt(file_bytes, file.content_type or "image/jpeg")
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI processing failed: {exc}",
        ) from exc

    # Deduct credits (raises 402 on race condition)
    await wallet_service.deduct_credits(
        user_id=current_user.id,
        amount=_SCAN_COST,
        feature=f"Receipt scan — {parsed.get('description', 'upload')}",
        db=db,
    )

    entry = LedgerEntry(
        user_id=current_user.id,
        entry_date=date.fromisoformat(parsed.get("entry_date", str(date.today()))),
        description=str(parsed.get("description", "Receipt")),
        category=str(parsed.get("category", "Other")),
        entry_type=str(parsed.get("entry_type", "expense")),
        amount=Decimal(str(parsed.get("amount", "0"))),
        source="receipt",
        confidence=float(parsed.get("confidence", 0.9)),
        raw_file_path=str(file_path),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.get("", response_model=list[LedgerEntryOut])
async def list_ledger_entries(
    filter_type: Literal["income", "expense", "all"] = Query(default="all", alias="filter"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LedgerEntryOut]:
    """Paginated list of ledger entries, newest first."""
    stmt = select(LedgerEntry).where(LedgerEntry.user_id == current_user.id)
    if filter_type != "all":
        stmt = stmt.where(LedgerEntry.entry_type == filter_type)
    stmt = stmt.order_by(col(LedgerEntry.created_at).desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.exec(stmt)
    return [LedgerEntryOut.model_validate(e) for e in result.all()]


@router.get("/export/csv")
async def export_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download all of the user's ledger entries as a CSV file."""
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.user_id == current_user.id)
        .order_by(col(LedgerEntry.entry_date).desc())
    )
    result = await db.exec(stmt)
    entries = result.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Description", "Category", "Type", "Amount (N)", "Source", "Confidence (%)"])
    for e in entries:
        writer.writerow([
            str(e.entry_date),
            e.description,
            e.category,
            e.entry_type.title(),
            str(e.amount),
            e.source.title(),
            str(round(e.confidence * 100)),
        ])

    buf.seek(0)
    filename = f"foid_ledger_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/pdf")
async def export_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download all of the user's ledger entries as a PDF file."""
    from fpdf import FPDF  # imported here — only used in this endpoint

    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.user_id == current_user.id)
        .order_by(col(LedgerEntry.entry_date).desc())
    )
    result = await db.exec(stmt)
    entries = result.all()

    pdf = FPDF(orientation="L", unit="mm", format="A4")  # landscape for wide table
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "FOID - Business Ledger Export", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0, 6,
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}  |  {len(entries)} entries",
        ln=True, align="C",
    )
    pdf.ln(4)

    # Column widths (landscape A4 usable width ~277mm)
    cols: list[tuple[str, int]] = [
        ("Date",        28),
        ("Description", 80),
        ("Category",    28),
        ("Type",        20),
        ("Amount (N)",  32),
        ("Source",      24),
        ("Confidence",  25),
    ]

    # Header row
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(22, 163, 74)
    pdf.set_text_color(255, 255, 255)
    for label, w in cols:
        pdf.cell(w, 7, label, border=0, fill=True, align="C")
    pdf.ln()

    # Data rows
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(30, 30, 30)
    for i, e in enumerate(entries):
        fill = i % 2 == 0
        if fill:
            pdf.set_fill_color(247, 248, 250)
        else:
            pdf.set_fill_color(255, 255, 255)
        desc = e.description[:55] + ("..." if len(e.description) > 55 else "")
        row = [
            str(e.entry_date),
            desc,
            e.category,
            e.entry_type.title(),
            f"{float(e.amount):,.2f}",
            e.source.title(),
            f"{round(e.confidence * 100)}%",
        ]
        for (_, w), text in zip(cols, row):
            pdf.cell(w, 6, text, border=0, fill=fill)
        pdf.ln()

    # Summary footer
    total_income  = sum(float(e.amount) for e in entries if e.entry_type == "income")
    total_expense = sum(float(e.amount) for e in entries if e.entry_type == "expense")
    net           = total_income - total_expense
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(
        0, 6,
        f"Total Income: N{total_income:,.2f}   |   Total Expenses: N{total_expense:,.2f}   |   Net: N{net:,.2f}",
        ln=True,
    )

    pdf_bytes = pdf.output()
    filename = f"foid_ledger_{date.today().isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/manual", response_model=LedgerEntryOut, status_code=status.HTTP_201_CREATED)
async def create_manual_entry(
    body: LedgerEntryCreate,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> LedgerEntryOut:
    """Add a ledger entry manually (no file upload). No credit cost."""
    entry = LedgerEntry(
        user_id=current_user.id,
        entry_date=body.entry_date,
        description=body.description,
        category=body.category,
        entry_type=body.entry_type,
        amount=body.amount,
        source="manual",
        confidence=1.0,
        raw_file_path=None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ledger_entry(
    entry_id: str,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a ledger entry owned by the current user."""
    result = await db.exec(
        select(LedgerEntry).where(
            LedgerEntry.id == entry_id,
            LedgerEntry.user_id == current_user.id,
        )
    )
    entry = result.first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    await db.delete(entry)
    await db.commit()


@router.patch("/{entry_id}", response_model=LedgerEntryOut)
async def update_ledger_entry(
    entry_id: str,
    body: LedgerEntryUpdate,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> LedgerEntryOut:
    """Edit a ledger entry (description, category, amount, entry_type, entry_date)."""
    result = await db.exec(
        select(LedgerEntry).where(
            LedgerEntry.id == entry_id,
            LedgerEntry.user_id == current_user.id,
        )
    )
    entry = result.first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    if body.description is not None:
        entry.description = body.description
    if body.category is not None:
        entry.category = body.category
    if body.amount is not None:
        entry.amount = body.amount
    if body.entry_type is not None:
        entry.entry_type = body.entry_type
    if body.entry_date is not None:
        entry.entry_date = body.entry_date

    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.post("/chat", response_model=ChatResponse)
async def ledger_chat(
    body: ChatRequest,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """AI chat about the user's business finances and identity. Costs 1 credit."""
    from datetime import date as _date
    from decimal import Decimal as _D
    import httpx as _httpx

    wallet = await _get_wallet(current_user.id, db)
    if wallet.balance < _CHAT_COST:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {_CHAT_COST}, have {wallet.balance}",
        )

    # ── Fetch context: ledger entries, credential ──────────────────────
    all_entries_result = await db.exec(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == current_user.id)
        .order_by(col(LedgerEntry.entry_date).desc())
        .limit(60)
    )
    all_entries = all_entries_result.all()

    # MTD aggregates from ledger
    today = _date.today()
    mtd = [e for e in all_entries if e.entry_date.year == today.year and e.entry_date.month == today.month]
    mtd_income  = sum(e.amount for e in mtd if e.entry_type == "income")
    mtd_expense = sum(e.amount for e in mtd if e.entry_type == "expense")

    # Top expense categories from ledger (all-time)
    cat_totals: dict[str, _D] = {}
    for e in all_entries:
        if e.entry_type == "expense":
            cat_totals[e.category] = cat_totals.get(e.category, _D("0")) + e.amount
    top_cats_ledger = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    # Credential state
    from ..models.credential import Credential
    from ..models.connected_bank import ConnectedBank
    from ..services import mono_service
    cred_result = await db.exec(select(Credential).where(Credential.user_id == current_user.id))
    cred = cred_result.first()
    cred_state = cred.state if cred else "unknown"
    cred_claims: dict = dict(cred.claims) if cred else {}

    # ── Fetch Mono bank transactions (last 60 days) ────────────────────
    from datetime import timedelta as _td
    start_str = (today - _td(days=60)).strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    banks_result = await db.exec(
        select(ConnectedBank).where(ConnectedBank.user_id == current_user.id)
    )
    connected_banks = banks_result.all()

    mono_tx_all: list[dict] = []
    mono_income_60d: float = 0.0
    mono_expense_60d: float = 0.0
    mono_cat_totals: dict[str, float] = {}
    mono_fetch_errors: list[str] = []   # track per-bank failures so the AI knows

    for bank in connected_banks:
        try:
            data = await mono_service.get_transactions(
                bank.mono_account_id, start=start_str, end=end_str, limit=200
            )
            txs = data.get("data", [])
            for tx in txs:
                naira = tx.get("amount", 0) / 100
                tx_type = tx.get("type", "")
                cat = tx.get("category") or "Other"
                if tx_type == "credit":
                    mono_income_60d += naira
                else:
                    mono_expense_60d += naira
                    mono_cat_totals[cat] = mono_cat_totals.get(cat, 0.0) + naira
                mono_tx_all.append({
                    "date": tx.get("date", "")[:10],
                    "type": tx_type,
                    "naira": naira,
                    "narration": tx.get("narration", "")[:60],
                    "category": cat,
                    "bank": bank.name,
                })
            if not txs:
                mono_fetch_errors.append(f"{bank.name}: returned 0 transactions (bank may have no activity in this window)")
            print(f"[AI chat] Mono {bank.name}: {len(txs)} transactions fetched")
        except Exception as _e:
            mono_fetch_errors.append(f"{bank.name}: fetch failed ({type(_e).__name__})")
            print(f"[AI chat] Mono {bank.name}: fetch error — {_e}")

    # Sort Mono transactions newest first
    mono_tx_all.sort(key=lambda t: t["date"], reverse=True)

    # MTD totals from Mono — current month only
    current_ym = today.strftime("%Y-%m")
    mono_mtd_income: float = sum(
        t["naira"] for t in mono_tx_all if t["type"] == "credit" and t["date"].startswith(current_ym)
    )
    mono_mtd_expense: float = sum(
        t["naira"] for t in mono_tx_all if t["type"] == "debit" and t["date"].startswith(current_ym)
    )

    # Combined MTD
    total_mtd_income  = float(mtd_income) + mono_mtd_income
    total_mtd_expense = float(mtd_expense) + mono_mtd_expense
    mtd_net = _D(str(total_mtd_income - total_mtd_expense))
    mtd_tax = max(_D("0"), (mtd_net * _D("0.075")).quantize(_D("1")))

    # Top spend categories — merge ledger + Mono
    merged_cats: dict[str, float] = {k: float(v) for k, v in top_cats_ledger}
    for cat, amt in mono_cat_totals.items():
        merged_cats[cat] = merged_cats.get(cat, 0.0) + amt
    top_cats = sorted(merged_cats.items(), key=lambda x: x[1], reverse=True)[:5]

    # Month-by-month breakdown from Mono transactions (for history questions)
    from collections import defaultdict as _dd
    mono_monthly: dict[str, dict[str, float]] = _dd(lambda: {"income": 0.0, "expense": 0.0})
    for t in mono_tx_all:
        ym = t["date"][:7]   # "YYYY-MM"
        if t["type"] == "credit":
            mono_monthly[ym]["income"] += t["naira"]
        else:
            mono_monthly[ym]["expense"] += t["naira"]

    mono_monthly_lines = ""
    if mono_monthly:
        sorted_months = sorted(mono_monthly.keys())
        mono_monthly_lines = "\n".join(
            f"  {ym}: IN ₦{v['income']:,.0f}  OUT ₦{v['expense']:,.0f}  NET ₦{v['income'] - v['expense']:,.0f}"
            for ym, v in [(m, mono_monthly[m]) for m in sorted_months]
        )
    else:
        mono_monthly_lines = "  (no Mono transaction data in the last 60 days)"

    # Recent 20 transactions — ledger + Mono, newest first
    ledger_lines = [
        f"  {e.entry_date} | {'IN ' if e.entry_type == 'income' else 'OUT'} | ₦{e.amount:,.0f} | {e.category} | {e.description} [Ledger]"
        for e in all_entries[:10]
    ]
    mono_lines = [
        f"  {t['date']} | {'IN ' if t['type'] == 'credit' else 'OUT'} | ₦{t['naira']:,.0f} | {t['category']} | {t['narration']} [{t['bank']} via Mono]"
        for t in mono_tx_all[:10]
    ]
    recent_lines = "\n".join(ledger_lines + mono_lines) or "  (no transactions in ledger or Mono)"

    top_cat_lines = "\n".join(f"  {cat}: ₦{amt:,.0f}" for cat, amt in top_cats) or "  (none)"

    connected_bank_names = ", ".join(b.name for b in connected_banks) if connected_banks else "none"
    mono_errors_block = (
        "\n=== MONO FETCH WARNINGS ===\n" + "\n".join(f"  {e}" for e in mono_fetch_errors)
        if mono_fetch_errors else ""
    )

    system_prompt = f"""You are FOID AI, a smart personal financial and identity assistant built into the FOID platform for Wema Bank.

=== USER PROFILE ===
Name: {current_user.first_name} {current_user.last_name}
Email: {current_user.email}
BVN verified: {"Yes" if cred_claims.get("bvn_validated") else "No"}
Identity verified: {"Yes" if cred_claims.get("identity_verified") else "No"}
Credential state: {cred_state}
AI credit balance: {wallet.balance} credits

=== CONNECTED BANKS (via Mono Open Banking) ===
Banks: {connected_bank_names}
Data window: last 60 days ({start_str} to {end_str})
{mono_errors_block}
=== THIS MONTH ({today.strftime("%B %Y")}) ===
Income  (Ledger + Mono): ₦{total_mtd_income:,.0f}
Expenses(Ledger + Mono): ₦{total_mtd_expense:,.0f}
Net:                     ₦{float(mtd_net):,.0f}
Est. tax (7.5%):         ₦{float(mtd_tax):,.0f}

=== MONTH-BY-MONTH (Mono Open Banking, last 60 days) ===
{mono_monthly_lines}

=== TOP EXPENSE CATEGORIES (Ledger + Mono, all time) ===
{top_cat_lines}

=== RECENT TRANSACTIONS (last 20, Ledger + Mono) ===
{recent_lines}

=== YOUR ROLE ===
- You help {current_user.first_name} understand their personal finances, spending patterns, income trends, tax estimates, credential status, and how to use FOID.
- You are warm, concise, and practical. Keep answers under 200 words unless a detailed breakdown is explicitly requested.
- You ONLY answer questions about: personal finances, budgeting, tax, spending, income, FOID credentials, identity verification, connected banks, transactions, and how to use FOID features.
- You MUST politely decline and redirect to finances if the user asks you to: write code, build programs, create images, play games, roleplay, give legal advice, discuss politics, or do ANYTHING unrelated to personal finance and FOID.
- CRITICAL: Never say "no transactions recorded" or "no data" if connected banks are listed above. If Mono returned 0 transactions, say the bank is connected but had no activity in the 60-day window — do NOT suggest the user connect a bank they have already connected.
- If MONO FETCH WARNINGS are present, tell the user honestly that there was a temporary issue fetching from that bank and they can retry.
- Never make up transaction data. Only use the figures provided above.
- Format numbers with ₦ and commas. Be encouraging when finances look healthy; be honest but constructive when they don't.
- You have access to real Open Banking transactions from the user's connected banks via Mono. Use them to give specific, data-driven advice."""

    # Build history for multi-turn context (cap at last 10 turns = 20 messages)
    history = [
        {"role": h.role, "content": h.content}
        for h in body.history[-20:]
    ]

    try:
        reply = await groq_service.chat(
            body.message,
            system_prompt=system_prompt,
            history=history or None,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI chat failed: {exc}",
        ) from exc

    # Deduct credit after successful AI call
    await wallet_service.deduct_credits(
        user_id=current_user.id,
        amount=_CHAT_COST,
        feature="AI chat",
        db=db,
    )
    await db.commit()
    await db.refresh(wallet)

    return ChatResponse(reply=reply, credits_remaining=wallet.balance)
