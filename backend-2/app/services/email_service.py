"""Email service — smart switch between console logger and Resend.

Logic
-----
* If ``RESEND_API_KEY`` is set in the environment (non-empty):
    → sends a real email via the Resend API (https://resend.com).
    → uses the branded HTML template when ``html=`` is supplied.
    → falls back to a plain-text body when only ``body=`` is given.
* If ``RESEND_API_KEY`` is blank (default dev setup):
    → prints a clearly formatted block to the terminal.
    → no external calls, no API keys required.

Usage
-----
    from app.services.email_service import send_email

    await send_email(
        to="user@example.com",
        subject="Your FOID OTP",
        body="Your code is: 123456",   # plain-text fallback
        html="<html>…</html>",         # branded HTML (optional)
    )
"""

from __future__ import annotations

import asyncio
import textwrap
from datetime import datetime, timezone


async def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
) -> None:
    """Send an email.

    Parameters
    ----------
    to:      Recipient address.
    subject: Email subject line.
    body:    Plain-text body (always required — used as console fallback and
             as Resend ``text`` field for email-client plain-text rendering).
    html:    Optional branded HTML body.  When ``RESEND_API_KEY`` is set and
             ``html`` is provided, the HTML version is sent.  When only
             ``body`` is provided, a plain-text email is sent via Resend.
    """
    from app.config import get_settings
    settings = get_settings()

    if settings.RESEND_API_KEY:
        await _send_via_resend(
            api_key=settings.RESEND_API_KEY,
            from_email=settings.FROM_EMAIL,
            to=to,
            subject=subject,
            body=body,
            html=html,
        )
    else:
        _log_to_console(to=to, subject=subject, body=body)


# ---------------------------------------------------------------------------
# Resend delivery
# ---------------------------------------------------------------------------

async def _send_via_resend(
    *,
    api_key: str,
    from_email: str,
    to: str,
    subject: str,
    body: str,
    html: str | None,
) -> None:
    """Call the Resend API inside a thread (the SDK is synchronous)."""
    import resend  # installed via `uv add resend`

    def _sync_send() -> None:
        resend.api_key = api_key
        payload: dict[str, str] = {
            "from": from_email,
            "to": to,
            "subject": subject,
            "text": body,
        }
        if html:
            payload["html"] = html
        resend.Emails.send(payload)  # type: ignore[attr-defined]

    await asyncio.to_thread(_sync_send)


# ---------------------------------------------------------------------------
# Console renderer — mirrors Django's console email backend output style
# ---------------------------------------------------------------------------

def _log_to_console(*, to: str, subject: str, body: str) -> None:
    """Print a clearly bordered email block to the terminal."""
    border = "-" * 72
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    wrapped_body = textwrap.indent(body.strip(), prefix="  ")

    message = (
        f"\n{border}\n"
        f"  📧 EMAIL (dev — not actually sent — set RESEND_API_KEY to send for real)\n"
        f"{border}\n"
        f"  To      : {to}\n"
        f"  Subject : {subject}\n"
        f"  Sent at : {timestamp}\n"
        f"{border}\n"
        f"{wrapped_body}\n"
        f"{border}\n"
    )
    print(message, flush=True)
