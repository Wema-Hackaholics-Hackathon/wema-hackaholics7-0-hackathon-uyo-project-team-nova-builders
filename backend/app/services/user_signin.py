"""Sign-in helpers for FOID user accounts: token issue, known devices and login alerts.

Every successful sign-in (password, password + 2FA code, passkey) goes through
`complete_sign_in`, so login alerts can't be skipped by one path.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token_expiry,
    generate_refresh_token,
    hash_refresh_token,
)
from app.models import Notification, RefreshToken, User, UserDevice
from app.services.email_service import send_email
from app.services.email_templates import login_alert


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def describe_agent(ua: str | None) -> str:
    """'Chrome on Windows' from a User-Agent — rough, for people, not for security decisions."""
    ua = ua or ""
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                            ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "A browser")
    system = next((name for key, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                                           ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if key in ua),
                  "an unknown device")
    return f"{browser} on {system}"


def _device_hash(user_id: str, device_id: str | None, ua: str | None) -> str:
    # The app sends a random per-browser id; without it, fall back to the User-Agent.
    return hashlib.sha256(f"{user_id}:{device_id or 'ua:' + (ua or '')}".encode()).hexdigest()


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    raw = generate_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_refresh_token(raw), expires_at=create_refresh_token_expiry()))
    return create_access_token(user.id), raw


async def complete_sign_in(db: AsyncSession, user: User, request: Request, device_id: str | None) -> tuple[str, str]:
    """Issue tokens, remember the device and — if it's new and alerts are on — email + notify. Commits."""
    ua = request.headers.get("user-agent")
    ip = client_ip(request)
    now = datetime.now(timezone.utc)
    h = _device_hash(user.id, device_id, ua)
    known = (await db.exec(select(UserDevice).where(UserDevice.user_id == user.id, UserDevice.device_hash == h))).first()
    # The very first device on record is the baseline (signup / first sign-in after this feature) — no alert.
    first_ever = known is None and (await db.exec(select(UserDevice.id).where(UserDevice.user_id == user.id))).first() is None
    if known:
        known.last_seen_at, known.ip, known.user_agent = now, ip, ua
        db.add(known)
    else:
        db.add(UserDevice(user_id=user.id, device_hash=h, user_agent=ua, ip=ip, first_seen_at=now, last_seen_at=now))
    alert = known is None and not first_ever and user.login_alerts
    device = describe_agent(ua)
    if alert:
        db.add(Notification(
            user_id=user.id,
            message="New sign-in to your account",
            change=f"Signed in from {device} (IP {ip})",
            reason="This device hasn't been used on your account before.",
            action="If this wasn't you, reset your password and turn on two-factor authentication.",
        ))
    tokens = await issue_tokens(db, user)
    await db.commit()
    if alert:
        when = now.strftime("%d %b %Y, %H:%M UTC")
        reset_url = f"{get_settings().PUBLIC_APP_URL.rstrip('/')}/forgot-password"
        subject, html = login_alert(to=user.email, first_name=user.first_name, when=when, device=device, ip=ip,
                                    reset_url=reset_url)
        await send_email(to=user.email, subject=subject, html=html,
                         body=(f"Hi {user.first_name},\n\nYour FOID account was signed in to from a new device.\n"
                               f"When: {when}\nDevice: {device}\nIP: {ip}\n\nIf this wasn't you, reset your password: "
                               f"{reset_url}\n\n— FOID"))
    return tokens


async def remember_device(db: AsyncSession, user: User, request: Request, device_id: str | None) -> None:
    """Record the signup device as known (no alert). Caller commits."""
    ua = request.headers.get("user-agent")
    now = datetime.now(timezone.utc)
    db.add(UserDevice(user_id=user.id, device_hash=_device_hash(user.id, device_id, ua), user_agent=ua,
                      ip=client_ip(request), first_seen_at=now, last_seen_at=now))
