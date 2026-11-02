"""Go live (KYB) — business side. /api/v1/business/organisations/{org_id}/kyb*

GET    /kyb                       status, details, required document types, uploaded documents, what's missing
PUT    /kyb/details               {rc_number?, tin?, registered_address?}            admin+
POST   /kyb/documents             multipart {type, file} — replaces that type          admin+
DELETE /kyb/documents/{doc_id}                                                          admin+
POST   /kyb                       submit for review (needs every required item)        owner

Details and documents can only change while the status is not_submitted or rejected.
FOID admins review through /api/v1/admin/organisations/{org_id}/kyb (routers/admin.py).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.core.api_errors import ApiError
from app.core.crypto import encrypt_bytes
from app.core.dependencies import require_verified_console_user
from app.models import ConsoleUser, KybDocument, Organisation
from app.routers.business import _member  # pyright: ignore[reportPrivateUsage]
from app.services import checks_service as cs
from app.services import kyb_service as kyb

router = APIRouter(prefix="/business", tags=["business-kyb"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[ConsoleUser, Depends(require_verified_console_user)]


class KybDetails(BaseModel):
    rc_number: str | None = Field(default=None, min_length=3, max_length=20, description="CAC registration number (RC/BN)")
    tin: str | None = Field(default=None, min_length=8, max_length=20, description="Tax identification number")
    registered_address: str | None = Field(default=None, min_length=10, max_length=300)


async def _org_and_docs(db: AsyncSession, org_id: str) -> tuple[Organisation, list[KybDocument]]:
    org = await db.get(Organisation, org_id)
    assert org is not None
    docs = list((await db.exec(select(KybDocument).where(KybDocument.org_id == org_id)
                               .order_by(KybDocument.created_at))).all())  # pyright: ignore[reportArgumentType]
    return org, docs


def _require_editable(org: Organisation) -> None:
    if not kyb.editable(org):
        msg = "Already approved" if org.kyb_status == "approved" else "Your documents are in review — wait for the result"
        raise ApiError(409, "kyb_locked", msg)


@router.get("/organisations/{org_id}/kyb")
async def get_kyb(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user)
    return kyb.view(*await _org_and_docs(db, org_id))


@router.put("/organisations/{org_id}/kyb/details")
async def save_details(org_id: str, body: KybDetails, user: CurrentUser, db: Db) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    org, docs = await _org_and_docs(db, org_id)
    _require_editable(org)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(org, k, v.strip() if isinstance(v, str) else v)
    db.add(org)
    await db.commit()
    return kyb.view(org, docs)


@router.post("/organisations/{org_id}/kyb/documents", status_code=201)
async def upload_document(
    org_id: str,
    user: CurrentUser,
    db: Db,
    type: Annotated[str, Form()],
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG, max 10 MB")],
) -> dict[str, Any]:
    await _member(db, org_id, user, "admin")
    org, _ = await _org_and_docs(db, org_id)
    _require_editable(org)
    if type not in kyb.DOC_TYPES:
        raise ApiError(422, "invalid_document_type", f"Unknown document type '{type}'", "type")
    data = await file.read(kyb.MAX_BYTES + 1)
    if len(data) > kyb.MAX_BYTES:
        raise ApiError(413, "file_too_large", "Files can be at most 10 MB", "file")
    if not data:
        raise ApiError(422, "empty_file", "The file is empty", "file")
    mime = kyb.detect_mime(data)
    if mime is None:
        raise ApiError(415, "unsupported_file", "Upload a PDF, JPEG or PNG", "file")

    old = (await db.exec(select(KybDocument).where(KybDocument.org_id == org_id, KybDocument.type == type))).first()
    if old:
        await db.delete(old)
        await db.flush()
    doc = KybDocument(org_id=org_id, type=type, filename=kyb.clean_filename(file.filename), mime=mime, size=len(data),
                      sha256=hashlib.sha256(data).hexdigest(), data_enc=encrypt_bytes(data), uploaded_by=user.id)
    db.add(doc)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="kyb.document_uploaded",
             target_type="kyb_document", target_id=doc.id, meta={"type": type, "size": len(data)})
    await db.commit()
    return kyb.doc_out(doc)


@router.delete("/organisations/{org_id}/kyb/documents/{doc_id}", status_code=204)
async def delete_document(org_id: str, doc_id: str, user: CurrentUser, db: Db) -> None:
    await _member(db, org_id, user, "admin")
    org, _ = await _org_and_docs(db, org_id)
    _require_editable(org)
    doc = await db.get(KybDocument, doc_id)
    if doc is None or doc.org_id != org_id:
        raise ApiError(404, "document_not_found", "No such document")
    await db.delete(doc)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="kyb.document_deleted",
             target_type="kyb_document", target_id=doc_id, meta={"type": doc.type})
    await db.commit()


@router.post("/organisations/{org_id}/kyb")
async def submit_kyb(org_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Send everything for review. Owner only — they attest the documents are genuine."""
    await _member(db, org_id, user, "owner")
    org, docs = await _org_and_docs(db, org_id)
    _require_editable(org)
    if missing := kyb.missing(org, docs):
        raise ApiError(422, "kyb_incomplete", "Add everything listed in details.missing before submitting", details={"missing": missing})
    org.kyb_status, org.kyb_submitted_at, org.kyb_note = "pending", datetime.now(timezone.utc), None
    db.add(org)
    cs.audit(db, org_id=org_id, actor_type="member", actor_id=user.id, action="kyb.submitted")
    await db.commit()
    await kyb.notify_owners(db, org)
    return kyb.view(org, docs)
