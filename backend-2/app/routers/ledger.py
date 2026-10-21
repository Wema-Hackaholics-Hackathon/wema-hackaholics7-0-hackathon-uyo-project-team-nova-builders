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
from ..core.dependencies import get_current_user
from ..models.ledger_entry import LedgerEntry
from ..models.user import User
from ..models.wallet import Wallet
from ..schemas.ledger import ChatRequest, ChatResponse, LedgerEntryOut, LedgerEntryUpdate
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
    current_user: User = Depends(get_current_user),
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


@router.patch("/{entry_id}", response_model=LedgerEntryOut)
async def update_ledger_entry(
    entry_id: str,
    body: LedgerEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LedgerEntryOut:
    """Edit a ledger entry (description, category, amount)."""
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

    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.post("/chat", response_model=ChatResponse)
async def ledger_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """AI chat about the user's business finances and identity. Costs 1 credit."""
    from datetime import date as _date
    from decimal import Decimal as _D

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

    # MTD aggregates
    today = _date.today()
    mtd = [e for e in all_entries if e.entry_date.year == today.year and e.entry_date.month == today.month]
    mtd_income  = sum(e.amount for e in mtd if e.entry_type == "income")
    mtd_expense = sum(e.amount for e in mtd if e.entry_type == "expense")
    mtd_net     = mtd_income - mtd_expense
    mtd_tax     = max(_D("0"), (mtd_net * _D("0.075")).quantize(_D("1")))

    # Top expense categories (all-time)
    cat_totals: dict[str, _D] = {}
    for e in all_entries:
        if e.entry_type == "expense":
            cat_totals[e.category] = cat_totals.get(e.category, _D("0")) + e.amount
    top_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    # Credential state
    from ..models.credential import Credential
    cred_result = await db.exec(select(Credential).where(Credential.user_id == current_user.id))
    cred = cred_result.first()
    cred_state = cred.state if cred else "unknown"
    cred_claims: dict = dict(cred.claims) if cred else {}

    # Recent 20 transactions for detail
    recent_lines = "\n".join(
        f"  {e.entry_date} | {'IN ' if e.entry_type == 'income' else 'OUT'} | ₦{e.amount:,.0f} | {e.category} | {e.description}"
        for e in all_entries[:20]
    ) or "  (no transactions yet)"

    top_cat_lines = "\n".join(f"  {cat}: ₦{amt:,.0f}" for cat, amt in top_cats) or "  (none)"

    system_prompt = f"""You are FOID AI, a smart personal financial and identity assistant built into the IDRA platform for Wema Bank.

=== USER PROFILE ===
Name: {current_user.first_name} {current_user.last_name}
Email: {current_user.email}
BVN verified: {"Yes" if cred_claims.get("bvn_validated") else "No"}
Identity verified: {"Yes" if cred_claims.get("identity_verified") else "No"}
Credential state: {cred_state}
AI credit balance: {wallet.balance} credits

=== THIS MONTH ({today.strftime("%B %Y")}) ===
Income:         ₦{mtd_income:,.0f}
Expenses:       ₦{mtd_expense:,.0f}
Net profit:     ₦{mtd_net:,.0f}
Estimated tax (7.5%): ₦{mtd_tax:,.0f}

=== TOP EXPENSE CATEGORIES (all time) ===
{top_cat_lines}

=== RECENT TRANSACTIONS (last 20) ===
{recent_lines}

=== YOUR ROLE ===
- You help {current_user.first_name} understand their personal finances, spending patterns, income trends, tax estimates, credential status, and how to use FOID.
- You are warm, concise, and practical. Keep answers under 200 words unless a detailed breakdown is explicitly requested.
- You ONLY answer questions about: finances, budgeting, tax, spending, income, IDRA credentials, identity verification, connected banks, and how to use FOID features.
- If the user asks you to generate code, write programs, create images, play games, discuss unrelated topics, or do anything outside personal finance and FOID — politely decline and redirect them to their finances.
- Never make up transaction data. Only use the figures provided above.
- Format numbers with ₦ and commas. Be encouraging when finances look healthy; be honest but constructive when they don't.
- If the user has no data yet, guide them to upload receipts or connect a bank account."""

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
