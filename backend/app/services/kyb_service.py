"""Go-live review (KYB): which documents a business must upload, and how we accept them.

Flow: not_submitted → (upload details + documents, submit) → pending → FOID admin
approves (live_enabled=True) or rejects with a reason → rejected → fix + resubmit.

Files are checked by their first bytes (not the name or the browser's content
type), limited to 10 MB, and stored Fernet-encrypted in the database. Only FOID
admins can download them; the business sees names and sizes only.
"""

from __future__ import annotations

import re
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ConsoleUser, KybDocument, Organisation, OrgMember
from app.services import checks_service as cs
from app.services.email_service import send_email
from app.services.email_templates import kyb_update

MAX_BYTES = 10 * 1024 * 1024

# type → (label, required)
DOC_TYPES: dict[str, tuple[str, bool]] = {
    "cac_certificate": ("CAC certificate of incorporation", True),
    "cac_status":      ("CAC status report (directors & shareholders)", True),
    "memart":          ("Memorandum & articles of association", True),
    "director_id":     ("A director's government ID", True),
    "proof_address":   ("Proof of business address", True),
    "licence":         ("Operating licence (if regulated)", False),
}
REQUIRED = [t for t, (_, req) in DOC_TYPES.items() if req]

_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def detect_mime(data: bytes) -> str | None:
    """PDF, JPEG or PNG by magic bytes; None for anything else."""
    return next((mime for sig, mime in _SIGNATURES if data.startswith(sig)), None)


def clean_filename(name: str | None) -> str:
    base = (name or "document").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .") or "document"
    return base[:120]


def missing(org: Organisation, docs: list[KybDocument]) -> list[str]:
    """What still blocks submission (field names / document types)."""
    have = {d.type for d in docs}
    out = [f for f in ("rc_number", "tin", "registered_address") if not getattr(org, f)]
    return out + [t for t in REQUIRED if t not in have]


def editable(org: Organisation) -> bool:
    return org.kyb_status in ("not_submitted", "rejected")


def doc_out(d: KybDocument) -> dict[str, Any]:
    return {"id": d.id, "type": d.type, "filename": d.filename, "mime": d.mime, "size": d.size,
            "uploaded_at": cs.iso(d.created_at)}


def view(org: Organisation, docs: list[KybDocument]) -> dict[str, Any]:
    return {
        "status": org.kyb_status,
        "live_enabled": org.live_enabled,
        "rc_number": org.rc_number,
        "tin": org.tin,
        "registered_address": org.registered_address,
        "submitted_at": cs.iso(org.kyb_submitted_at),
        "reviewed_at": cs.iso(org.kyb_reviewed_at),
        "note": org.kyb_note if org.kyb_status == "rejected" else None,
        "editable": editable(org),
        "document_types": [{"type": t, "label": label, "required": req} for t, (label, req) in DOC_TYPES.items()],
        "documents": [doc_out(d) for d in docs],
        "missing": missing(org, docs),
    }


async def notify_owners(db: AsyncSession, org: Organisation) -> None:
    """Email every owner about the current review status (received / approved / rejected)."""
    owners = (await db.exec(select(ConsoleUser).join(OrgMember, OrgMember.console_user_id == ConsoleUser.id)  # pyright: ignore[reportArgumentType]
                            .where(OrgMember.org_id == org.id, OrgMember.role == "owner"))).all()
    for o in owners:
        subject, html = kyb_update(first_name=o.first_name, to=o.email, org_name=org.name,
                                   status=org.kyb_status, note=org.kyb_note)
        await send_email(to=o.email, subject=subject, html=html,
                         body=f"Hi {o.first_name},\n\n{subject}.\n{org.kyb_note or ''}\n\n— FOID")
