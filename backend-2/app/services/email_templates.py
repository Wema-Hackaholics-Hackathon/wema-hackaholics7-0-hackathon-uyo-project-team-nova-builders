"""FOID branded HTML email templates.

All templates follow the same layout:
  - White card centred on a light-grey background
  - Purple (#C800DE) top header band with logo + wordmark
  - Clean body with FOID purple CTAs
  - Muted footer

Each function returns a (subject, html) tuple.
"""

from __future__ import annotations

# FOID logo-white as a tiny base64 PNG so the header works even in email clients
# that block external images.  We also reference a hosted URL as a fallback src.
_LOGO_B64 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAB8AAAApCAYAAADNjfKJAAAACXBIWXMAAAsTAAALEwEAmpwY"
    "AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAOdEVYdFNvZnR3YXJlAEZpZ21hnrGW"
    "YwAAAehJREFUeAG9loFVwjAQhv/6GIANDBvgBNYJhA1wAnEDmECYQEfACawT6AbUCdQJ4h1p"
    "H2loS3JJ+d478WnTj+s1l8twQbTWY/qYUdxS/GFoWEixpHin+NFHliMMAN04h8kur6KNLySS"
    "cXY5xbOTXSe8Tpy5Vb97mOzGAcvfguUkVI5Qyo5/ZOeusuq3oFCIp8yybMK/jFpk/PimMNkt"
    "EPY4fVijRapatkNq9rbTzlwhro4+NLK+QlM+JFuq9Ss65Klra1NSrNw/XkJeUtxR1r/okSuk"
    "h4VzEpdt/7Tl10gv5ow7e/gVhqGkuOkTu3KFNBSVuPReoePh5rREKNociTHSlTZtOYi6w4Uu"
    "5JepgDkad/U24i/QtqV60WYQ8MlwU107ttY2xqQA7dnMC4oP/qSMCks4pajP9Ny6Pmg0apMX"
    "OD7O0hLmMMcsDxOq437fEMi5Tg9w6kexgBkkZvB7L3aQ4tRPgkIotOgxQljzAgkJxEyOQOr2"
    "GnucNnaDL4fpVZv9GfMFJkG9vCJF5luJ+IA2U6uUvRb09BrOXEFGPSyE9XJHLuVJ/LgtuUI4"
    "a3cMljASyDnjDRLAct8X5tD/SSzv30I5H5Xz2BqfoPtb62FEwlDQzT+7pDF72Fe+t4QnY9LQ"
    "8pXkRErBP53BTRQPqBdLAAAAAElFTkSuQmCC"
)

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
                    <img src="{_LOGO_B64}" alt="FOID" width="24" height="32"
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
