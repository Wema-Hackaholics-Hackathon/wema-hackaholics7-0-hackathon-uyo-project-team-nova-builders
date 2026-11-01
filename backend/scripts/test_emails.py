"""Test script — send all three FOID branded email templates.

Usage
-----
From the backend-2/ directory:

    uv run python scripts/test_emails.py your@email.com

If RESEND_API_KEY is set in .env (or the shell environment), the emails are
delivered to the inbox you provide.  If not, they are printed to the terminal
so you can inspect the plain-text fallback.

Templates tested
----------------
1. Email verification OTP
2. Password reset OTP
3. Welcome / account confirmed
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running the script from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env so RESEND_API_KEY / FROM_EMAIL are picked up automatically.
from dotenv import load_dotenv  # type: ignore[import-untyped]
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/test_emails.py your@email.com")
        sys.exit(1)

    recipient = sys.argv[1]

    from app.services.email_service import send_email
    from app.services.email_templates import (
        email_verification,
        password_reset,
        welcome,
    )
    from app.config import get_settings

    settings = get_settings()
    mode = "Resend API" if settings.RESEND_API_KEY else "console (no RESEND_API_KEY set)"
    print(f"\n🚀 Sending 3 test emails to: {recipient}")
    print(f"   Delivery mode : {mode}")
    if settings.RESEND_API_KEY:
        print(f"   From          : {settings.FROM_EMAIL}")
    print()

    # ── 1. Email verification OTP ─────────────────────────────────────────
    otp_verify = "847291"
    subject1, html1 = email_verification(
        first_name="Amara",
        otp=otp_verify,
        to=recipient,
    )
    await send_email(
        to=recipient,
        subject=subject1,
        body=(
            f"Hi Amara, welcome to FOID!\n\n"
            f"Your email verification code is:  {otp_verify}\n\n"
            f"This code expires in 30 minutes.\n\n— The FOID Team"
        ),
        html=html1,
    )
    print(f"  ✅ [1/3] Verification OTP sent  — subject: {subject1!r}")

    # ── 2. Password reset OTP ─────────────────────────────────────────────
    otp_reset = "512034"
    subject2, html2 = password_reset(
        first_name="Amara",
        otp=otp_reset,
        to=recipient,
    )
    await send_email(
        to=recipient,
        subject=subject2,
        body=(
            f"Hi Amara,\n\n"
            f"Your FOID password reset code is:  {otp_reset}\n\n"
            f"This code expires in 10 minutes.\n\n— The FOID Team"
        ),
        html=html2,
    )
    print(f"  ✅ [2/3] Password reset OTP sent — subject: {subject2!r}")

    # ── 3. Welcome / account confirmed ───────────────────────────────────
    subject3, html3 = welcome(
        first_name="Amara",
        to=recipient,
        dashboard_url="http://localhost:5173/dashboard",
    )
    await send_email(
        to=recipient,
        subject=subject3,
        body=(
            f"Hi Amara, welcome to FOID! 🎉\n\n"
            f"Your email is now verified and your FOID credential has been issued.\n\n"
            f"Head to your dashboard: http://localhost:5173/dashboard\n\n"
            f"— The FOID Team"
        ),
        html=html3,
    )
    print(f"  ✅ [3/3] Welcome email sent      — subject: {subject3!r}")

    print()
    if settings.RESEND_API_KEY:
        print("📬 All 3 emails dispatched via Resend. Check your inbox!")
    else:
        print("📋 Printed to terminal above (RESEND_API_KEY not set).")
    print()


if __name__ == "__main__":
    asyncio.run(main())
