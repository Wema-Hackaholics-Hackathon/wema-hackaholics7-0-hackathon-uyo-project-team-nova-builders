"""Email service — console logger in development, Resend in production.

In development (ENV=development) every outgoing email is printed to the
terminal in a clear, bordered format — exactly like Django's console email
backend.  No SMTP, no API keys, no setup required.

In production (ENV=production) the send_email() function is where you plug
in Resend (or any other provider).  The call signature never changes, so
all callers remain untouched when you make that swap.

Usage
-----
    from app.services.email_service import send_email

    await send_email(
        to="user@example.com",
        subject="Your password reset code",
        body="Your OTP is: 123456\\n\\nExpires in 10 minutes.",
    )
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone


async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email.

    Development: prints a formatted block to the terminal via logging.
    Production:  replace the stub below with a real provider (e.g. Resend).
    """
    from app.config import get_settings
    settings = get_settings()

    if settings.ENV != "production":
        _log_to_console(to=to, subject=subject, body=body)
        return

    # ------------------------------------------------------------------ #
    # PRODUCTION — swap this block for your real mailer when ready.       #
    # Example with Resend:                                                 #
    #                                                                      #
    #   import resend                                                      #
    #   resend.api_key = settings.RESEND_API_KEY                          #
    #   resend.Emails.send({                                               #
    #       "from": settings.FROM_EMAIL,                                  #
    #       "to": to,                                                      #
    #       "subject": subject,                                            #
    #       "text": body,                                                  #
    #   })                                                                 #
    # ------------------------------------------------------------------ #
    print(
        f"[email_service] WARNING: send_email() called in production but no mailer is configured. "
        f"To: {to} | Subject: {subject}",
        flush=True,
    )


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
        f"  📧 EMAIL (development — not actually sent)\n"
        f"{border}\n"
        f"  To      : {to}\n"
        f"  Subject : {subject}\n"
        f"  Sent at : {timestamp}\n"
        f"{border}\n"
        f"{wrapped_body}\n"
        f"{border}\n"
    )
    print(message, flush=True)
