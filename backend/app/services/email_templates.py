"""FOID branded HTML email templates.

All templates follow the same layout:
  - White card centred on a light-grey background
  - Purple (#C800DE) top header band with logo + wordmark
  - Clean body with FOID purple CTAs
  - Muted footer

Each function returns a (subject, html) tuple.
"""

from __future__ import annotations

from html import escape
from pathlib import Path


LOGO_CID = "foid-logo"


def _load_logo() -> bytes | None:
    """logo-white.png from the repo (frontend/public) or next to this module; None if missing."""
    candidates = [
        Path(__file__).resolve().parents[3] / "frontend" / "public" / "logo-white.png",
        Path(__file__).resolve().parent / "logo-white.png",
    ]
    for path in candidates:
        if path.exists():
            return path.read_bytes()
    return None


# Sent as an inline (cid:) attachment by email_service. Gmail and Outlook block
# data: URIs and can't reach localhost, so neither of those shows the logo.
LOGO_PNG = _load_logo()


def _logo_src() -> str:
    """EMAIL_LOGO_URL (a public https image) if set, otherwise the inline attachment."""
    from app.config import get_settings
    return get_settings().EMAIL_LOGO_URL or (f"cid:{LOGO_CID}" if LOGO_PNG else "")

_PURPLE     = "#C800DE"
_PURPLE_MID = "#9b00d9"
_PURPLE_BG  = "#fdf4ff"
_DARK       = "#18181b"
_MUTED      = "#71717a"
_BORDER     = "#e4e4e7"


def _base(*, preheader: str, body_html: str) -> str:
    """Wrap body_html in the shared FOID email chrome."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light" />
  <title>FOID</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>
    body {{ margin:0; padding:0; background:#f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
    a {{ color:{_PURPLE_MID}; text-decoration:none; }}
    @media (prefers-color-scheme: dark) {{ body {{ background:#18181b; }} }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;">
  <!-- preheader (hidden) -->
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preheader}&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌</div>

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f4f5;padding:32px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {_BORDER};">

          <!-- Header band -->
          <tr>
            <td style="background:{_PURPLE};padding:20px 28px;">
              <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{_logo_src()}" alt="FOID" width="24" height="32"
                         style="display:inline-block;vertical-align:middle;margin-right:10px;" />
                    <span style="font-size:22px;font-weight:900;color:#ffffff;vertical-align:middle;letter-spacing:-0.3px;">FOID</span>
                  </td>
                  <td align="right">
                    <span style="font-size:11px;color:rgba(255,255,255,0.65);letter-spacing:1.5px;text-transform:uppercase;vertical-align:middle;">Identity &amp; Financial Trust</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 36px 28px 36px;">
              {body_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#fafafa;border-top:1px solid {_BORDER};padding:20px 36px;text-align:center;">
              <p style="margin:0 0 6px 0;font-size:12px;color:{_MUTED};">
                FOID · Identity &amp; Financial Trust Platform
              </p>
              <p style="margin:0;font-size:11px;color:#a1a1aa;">
                If you didn't request this email, you can safely ignore it.
                This message was sent to <strong>__RECIPIENT__</strong>.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>
</body>
</html>"""


def _otp_block(otp: str) -> str:
    """Renders a large centred OTP code block."""
    return f"""
      <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:24px 0;">
        <tr>
          <td align="center">
            <div style="display:inline-block;background:{_PURPLE_BG};border:2px dashed {_PURPLE};border-radius:12px;padding:18px 40px;">
              <span style="font-size:36px;font-weight:900;letter-spacing:10px;color:{_PURPLE};font-family:monospace;">{otp}</span>
            </div>
          </td>
        </tr>
      </table>"""


def _cta_button(href: str, label: str) -> str:
    return f"""
      <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:28px 0 12px 0;">
        <tr>
          <td align="center">
            <a href="{href}" style="display:inline-block;background:{_PURPLE};color:#ffffff;font-size:15px;font-weight:700;padding:14px 40px;border-radius:50px;text-decoration:none;letter-spacing:-0.1px;">{label}</a>
          </td>
        </tr>
      </table>"""


def _h1(text: str) -> str:
    return f'<h1 style="margin:0 0 8px 0;font-size:22px;font-weight:800;color:{_DARK};letter-spacing:-0.3px;">{text}</h1>'


def _p(text: str, *, muted: bool = False, size: int = 15) -> str:
    colour = _MUTED if muted else _DARK
    return f'<p style="margin:0 0 16px 0;font-size:{size}px;line-height:1.65;color:{colour};">{text}</p>'


def _divider() -> str:
    return f'<hr style="border:none;border-top:1px solid {_BORDER};margin:24px 0;" />'


# ── Template 1: Email verification OTP ──────────────────────────────────────

def email_verification(*, first_name: str, otp: str, to: str) -> tuple[str, str]:
    subject = "Verify your FOID email address"
    body = (
        _h1("Verify your email")
        + _p(f"Hi {first_name}, welcome to FOID! 👋<br />Enter the code below inside the app to activate your account.")
        + _otp_block(otp)
        + _p("This code expires in <strong>30 minutes</strong>.", muted=True, size=13)
        + _divider()
        + _p("FOID keeps your identity and finances secure — you're in safe hands.", muted=True, size=13)
    )
    html = _base(preheader=f"Your FOID verification code is {otp}", body_html=body).replace("__RECIPIENT__", to)
    return subject, html


# ── Template 2: Password reset OTP ──────────────────────────────────────────

def password_reset(*, first_name: str, otp: str, to: str) -> tuple[str, str]:
    subject = "Your FOID password reset code"
    body = (
        _h1("Reset your password")
        + _p(f"Hi {first_name}, we received a request to reset your FOID password.")
        + _p("Use the code below inside the app to set a new password:")
        + _otp_block(otp)
        + _p("This code expires in <strong>10 minutes</strong>.", muted=True, size=13)
        + _divider()
        + _p("If you didn't request a password reset, your account is safe — just ignore this email.", muted=True, size=13)
    )
    html = _base(preheader=f"Your FOID password reset code is {otp}", body_html=body).replace("__RECIPIENT__", to)
    return subject, html


# ── Template 3: Welcome / account confirmed ──────────────────────────────────

def welcome(*, first_name: str, to: str, dashboard_url: str = "https://app.foid.ng/dashboard") -> tuple[str, str]:
    subject = f"Welcome to FOID, {first_name}! Your identity credential is ready"
    body = (
        _h1(f"Welcome to FOID, {first_name}! 🎉")
        + _p("Your email is now verified and your FOID identity credential has been issued.")
        + f"""
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:{_PURPLE_BG};border-radius:12px;padding:20px;margin:20px 0;">
          <tr>
            <td>
              <p style="margin:0 0 10px 0;font-size:14px;font-weight:700;color:{_DARK};">What you can do now:</p>
              <p style="margin:0 0 6px 0;font-size:14px;color:{_DARK};">✅ &nbsp;Connect your bank accounts via Open Banking</p>
              <p style="margin:0 0 6px 0;font-size:14px;color:{_DARK};">✅ &nbsp;Scan receipts and let AI manage your bookkeeping</p>
              <p style="margin:0 0 6px 0;font-size:14px;color:{_DARK};">✅ &nbsp;Share your verified credential with fintechs instantly</p>
              <p style="margin:0;font-size:14px;color:{_DARK};">✅ &nbsp;Chat with your AI financial assistant</p>
            </td>
          </tr>
        </table>
        """
        + _cta_button(dashboard_url, "Go to my dashboard →")
        + _p("Need help? Chat with your FOID AI assistant right inside the dashboard.", muted=True, size=13)
    )
    html = _base(preheader=f"Welcome to FOID, {first_name}! Your credential is ready.", body_html=body).replace("__RECIPIENT__", to)
    return subject, html


# ── Business console: verification + password reset codes ───────────────────

def console_code(*, first_name: str, otp: str, to: str, purpose: str) -> tuple[str, str]:
    """purpose: verify_email | reset_password — for FOID business console accounts."""
    if purpose == "verify_email":
        subject, title = "Verify your FOID Console email", "Verify your console email"
        intro = f"Hi {first_name}, enter this code in the FOID Console to finish setting up your business account."
        ttl = "30 minutes"
    else:
        subject, title = "Your FOID Console password reset code", "Reset your console password"
        intro = f"Hi {first_name}, use this code in the FOID Console to set a new password."
        ttl = "10 minutes"
    body = (
        _h1(title) + _p(intro) + _otp_block(otp)
        + _p(f"This code expires in <strong>{ttl}</strong>.", muted=True, size=13)
        + _divider()
        + _p("This is for your FOID business console account, which is separate from any personal FOID account. "
             "If you didn't ask for this, ignore this email.", muted=True, size=13)
    )
    html = _base(preheader=f"Your FOID Console code is {otp}", body_html=body).replace("__RECIPIENT__", to)
    return subject, html


# ── Business console: go-live review updates ────────────────────────────────

def kyb_update(*, first_name: str, to: str, org_name: str, status: str, note: str | None = None) -> tuple[str, str]:
    """status: pending (received) | approved | rejected."""
    if status == "pending":
        subject, title = f"We've received {org_name}'s documents", "Documents received"
        text = "Thanks — our team is reviewing your business documents. This usually takes 1–2 business days. Keep building in Test mode meanwhile."
    elif status == "approved":
        subject, title = f"{org_name} is approved for Live", "You're approved for Live 🎉"
        text = "Your business documents are approved. Switch to Live in the FOID Console and create a live key to start verifying real customers."
    else:
        subject, title = f"Action needed: {org_name}'s go-live review", "We need a few changes"
        text = "We couldn't approve your documents yet. Open Go live in the FOID Console, fix what's listed below and submit again."
    body = _h1(title) + _p(f"Hi {first_name},") + _p(text)
    if note:
        body += _p(f"<strong>Reviewer's note:</strong> {escape(note)}")
    html = _base(preheader=title, body_html=body).replace("__RECIPIENT__", to)
    return subject, html


# ── Business console: team invite + API key alert ────────────────────────────

def console_invite(*, to: str, org_name: str, inviter: str, role: str, link: str) -> tuple[str, str]:
    subject = f"{inviter} invited you to {org_name} on FOID Console"
    body = (
        _h1(f"Join {escape(org_name)} on FOID")
        + _p(f"{escape(inviter)} invited you to the FOID Console for <strong>{escape(org_name)}</strong> as <strong>{escape(role)}</strong>.")
        + _cta_button(link, "Accept invitation")
        + _p("The link works once and expires in 7 days. If you weren't expecting this, ignore it.", muted=True, size=13)
    )
    return subject, _base(preheader=subject, body_html=body).replace("__RECIPIENT__", to)


def api_key_alert(*, to: str, org_name: str, actor: str, env: str, key_name: str, hint: str) -> tuple[str, str]:
    subject = f"New {env} API key created for {org_name}"
    body = (
        _h1("A new API key was created")
        + _p(f"<strong>{escape(actor)}</strong> created the {escape(env)} key <strong>{escape(key_name)}</strong> "
             f"(<code>{escape(hint)}</code>) for {escape(org_name)}.")
        + _p("If that wasn't expected, revoke it in FOID Console → API keys & webhooks.", muted=True, size=13)
    )
    return subject, _base(preheader=subject, body_html=body).replace("__RECIPIENT__", to)


def login_alert(*, to: str, first_name: str, when: str, device: str, ip: str, reset_url: str) -> tuple[str, str]:
    """A sign-in from a device FOID hasn't seen on this account before."""
    subject = "New sign-in to your FOID account"
    body = (
        _h1("New sign-in to FOID")
        + _p(f"Hi {escape(first_name)}, your account was just signed in to from a device we haven't seen before.")
        + _p(f"<strong>When:</strong> {escape(when)}<br><strong>Device:</strong> {escape(device)}"
             f"<br><strong>IP address:</strong> {escape(ip)}", size=14)
        + _p("If this was you, you don't need to do anything.")
        + _p("If it wasn't, reset your password now and turn on two-factor authentication in Settings.", size=14)
        + _cta_button(reset_url, "Reset my password")
        + _p("You can turn these emails off in Settings → Security → Login alerts.", muted=True, size=13)
    )
    return subject, _base(preheader=subject, body_html=body).replace("__RECIPIENT__", to)
