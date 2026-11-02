"""Emails the console sends about a business: invites and API key alerts."""

from __future__ import annotations

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ApiKey, ConsoleUser, Organisation, OrgMember
from app.services.email_service import send_email
from app.services.email_templates import api_key_alert, console_invite


async def key_created(db: AsyncSession, org: Organisation, actor: ConsoleUser, key: ApiKey) -> None:
    """Settings → Security → "Email alert on new API key creation" (on by default). Owners and admins."""
    if not org.alert_on_key_create:
        return
    people = (await db.exec(select(ConsoleUser).join(OrgMember, col(OrgMember.console_user_id) == ConsoleUser.id)
                            .where(OrgMember.org_id == org.id, col(OrgMember.role).in_(["owner", "admin"])))).all()
    actor_name = f"{actor.first_name} {actor.last_name}"
    for p in people:
        subject, html = api_key_alert(to=p.email, org_name=org.name, actor=actor_name, env=key.env, key_name=key.name, hint=key.prefix)
        await send_email(to=p.email, subject=subject, html=html,
                         body=f"{actor_name} created the {key.env} API key {key.name} ({key.prefix}) for {org.name}.")


async def invite(*, to: str, org: Organisation, inviter: ConsoleUser, role: str, link: str) -> None:
    name = f"{inviter.first_name} {inviter.last_name}"
    subject, html = console_invite(to=to, org_name=org.name, inviter=name, role=role, link=link)
    await send_email(to=to, subject=subject, html=html,
                     body=f"{name} invited you to {org.name} on FOID Console as {role}.\n\nAccept: {link}\n\nThe link expires in 7 days.")
