"""The business console's notification bell.

notify() stages one row per team member whose role is at least `min_role`
(caller commits, so the notification lands with the change it describes).
Who sees what:
  owners/admins   go-live decisions, invoices, API keys, new team members
  developers+     webhook endpoints failing
  reviewers+      people revoking consent
  everyone        business deactivated / reactivated
"""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ConsoleNotification, OrgMember
from app.services.checks_service import iso, utcnow

_RANK = {"viewer": 0, "reviewer": 1, "developer": 2, "admin": 3, "owner": 4}


async def notify(db: AsyncSession, org_id: str, kind: str, title: str, body: str = "", *, link: str | None = None,
                 min_role: str = "viewer", exclude: str | None = None, ref: str | None = None,
                 once_per: timedelta | None = None) -> int:
    """Stage notifications. `exclude`: the person who did it (they already know).
    `once_per`: skip people who already have an unread one of this kind+ref that recent."""
    members = (await db.exec(select(OrgMember).where(OrgMember.org_id == org_id))).all()
    made = 0
    for m in members:
        if _RANK[m.role] < _RANK[min_role] or m.console_user_id == exclude:
            continue
        if once_per is not None:
            dup = (await db.exec(select(ConsoleNotification.id).where(
                ConsoleNotification.console_user_id == m.console_user_id, ConsoleNotification.org_id == org_id,
                ConsoleNotification.kind == kind, ConsoleNotification.ref == ref,
                col(ConsoleNotification.read_at).is_(None), ConsoleNotification.created_at >= utcnow() - once_per))).first()
            if dup:
                continue
        db.add(ConsoleNotification(org_id=org_id, console_user_id=m.console_user_id, kind=kind, title=title,
                                   body=body, link=link, ref=ref))
        made += 1
    return made


def out(n: ConsoleNotification) -> dict[str, object]:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "read": n.read_at is not None, "created_at": iso(n.created_at)}
