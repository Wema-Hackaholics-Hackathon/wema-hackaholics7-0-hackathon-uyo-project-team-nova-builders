"""Linking a business's subjects to a FOID account.

A business can verify someone who has no FOID account (a "subject"). If that
person later joins FOID, their subjects are linked to the new account so they
can SEE which businesses verified them and REVOKE access from "Connected apps".

Linking never shares anything new with the business: the business keeps only
what it already collected under its grant. To read FOID-held data (e.g. the trust
report) the business must ask again and the person must approve.

When is a subject linked to a user?  The NIN at FOID signup is only
format-checked, so a NIN match alone is NOT enough (anyone can type someone
else's NIN). We require:

  1. subject.nin_hash == hash(user.nin) AND the subject's NIN was verified by a
     lookup, AND one of:
  2a. email: the user's email is verified on FOID and equals the email the
      business recorded for the subject                    → link_method "email_nin"
  2b. face:  the user has an enrolled liveness face and the subject has a
      liveness face, and the two match (SFace cosine)       → link_method "face_nin"

Or, explicitly: the person signs in to FOID inside a business's hosted flow and
chooses "Share my FOID identity"                            → link_method "foid_share"

Evaluated from both sides:
  link_subjects_for_user(user)  — on FOID email verification and liveness enrolment
  link_user_for_subject(subject) — when a business verifies a NIN or a liveness face

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AuditLog,
    ConsentGrant,
    Credential,
    FaceEnrolment,
    Notification,
    Organisation,
    Subject,
    SubjectFace,
    User,
)
from app.services import face_match_service as fm
from app.services.webhook_service import enqueue_event


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def link(db: AsyncSession, subject: Subject, user: User, method: str) -> None:
    """Attach a subject to a FOID user (caller commits)."""
    subject.user_id, subject.linked_at, subject.link_method = user.id, _now(), method
    subject.updated_at = _now()
    db.add(subject)
    for g in (await db.exec(select(ConsentGrant).where(ConsentGrant.subject_id == subject.id))).all():
        g.user_id = user.id
        db.add(g)
    org = await db.get(Organisation, subject.org_id)
    org_name = org.name if org else "A business"
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message=f"{org_name} verified you through FOID",
        change="connected app linked",
        reason=(
            f"{org_name} ran identity checks on you before you joined FOID. "
            "Their access is now listed under Connected apps."
        ),
        action="Review what they can see, or revoke their access, in Connected apps.",
    ))
    db.add(AuditLog(
        org_id=subject.org_id, actor_type="system", action="subject.linked",
        target_type="subject", target_id=subject.id, meta={"user_id": user.id, "method": method},
    ))
    await enqueue_event(
        db, org_id=subject.org_id, env=subject.env, event_type="subject.linked", subject_id=subject.id,
        data={"subject_id": subject.id, "customer_ref": subject.customer_ref, "foid_account": True},
    )


async def _email_verified(db: AsyncSession, user: User) -> bool:
    cred = (await db.exec(select(Credential).where(Credential.user_id == user.id))).first()
    return bool(cred and cred.claims.get("email_verified"))  # type: ignore[union-attr]


async def _link_method(db: AsyncSession, subject: Subject, user: User) -> str | None:
    """Evidence rules (the NIN match is checked by the callers)."""
    if (
        subject.email
        and subject.email.strip().lower() == user.email.strip().lower()
        and await _email_verified(db, user)
    ):
        return "email_nin"
    enrolment = (await db.exec(select(FaceEnrolment).where(FaceEnrolment.user_id == user.id))).first()
    face = (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == subject.id))).first()
    if enrolment is not None and face is not None:
        score = fm.cosine(fm.decrypt_template(enrolment.template_enc), fm.decrypt_template(face.template_enc))
        if fm.is_match(score):
            return "face_nin"
    return None


async def link_subjects_for_user(db: AsyncSession, user: User) -> list[Subject]:
    """Link this user's unlinked, NIN-verified subjects that pass the evidence rules (caller commits)."""
    if not user.nin_hash:
        return []
    candidates = (await db.exec(
        select(Subject).where(
            Subject.user_id == None,  # noqa: E711
            Subject.env == "live",   # sandbox data never attaches to real people automatically
            Subject.nin_hash == user.nin_hash,
            Subject.nin_verified == True,  # noqa: E712
        )
    )).all()
    linked: list[Subject] = []
    for s in candidates:
        method = await _link_method(db, s, user)
        if method:
            await link(db, s, user, method)
            linked.append(s)
    return linked


async def link_user_for_subject(db: AsyncSession, subject: Subject) -> User | None:
    """A business just verified this subject's NIN or face: is it an existing FOID user? (caller commits)"""
    if subject.env != "live" or subject.user_id or not subject.nin_verified or not subject.nin_hash:
        return None
    user = (await db.exec(select(User).where(User.nin_hash == subject.nin_hash))).first()
    if user is None:
        return None
    method = await _link_method(db, subject, user)
    if method is None:
        return None
    await link(db, subject, user, method)
    return user
