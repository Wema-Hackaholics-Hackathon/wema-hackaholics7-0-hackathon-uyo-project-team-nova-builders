"""Shared PDF branding utilities for FOID document generation.

Provides _draw_foid_header() which paints the standard purple header band
with the FOID logo-white icon and wordmark on every generated PDF.

Usage (portrait A4, margins 14mm):
    pdf = FPDF(...)
    pdf.add_page()
    pdf.set_margins(14, 14, 14)
    band_h = _draw_foid_header(pdf, title="My Document Title", subtitle="user name | date")
    pdf.set_y(band_h + 6)   # start content below the band

Usage (landscape A4, margins 12mm):
    band_h = _draw_foid_header(pdf, title="...", subtitle="...", landscape=True)
    pdf.set_y(band_h + 8)
"""

from __future__ import annotations

import base64
import io

# ── logo-white.png embedded as base64 so the backend has zero filesystem
# dependency on the frontend public/ directory at runtime. ─────────────────
_LOGO_WHITE_B64 = (
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


def _logo_bytes() -> bytes:
    """Return the raw PNG bytes for logo-white.png."""
    return base64.b64decode(_LOGO_WHITE_B64)


# FOID purple brand colour
_PURPLE = (200, 0, 222)


def draw_foid_header(
    pdf,  # fpdf.FPDF instance
    title: str,
    subtitle: str = "",
    *,
    landscape: bool = False,
) -> float:
    """Draw the FOID purple header band on the current page.

    Places logo-white icon on the left, bold title text beside it,
    and an optional subtitle line underneath on the right.

    Returns the band height in mm so callers can position content below it.
    """
    page_w: float = 297.0 if landscape else 210.0
    band_h: float = 26.0

    # ── Purple band ───────────────────────────────────────────────────
    pdf.set_fill_color(*_PURPLE)
    pdf.rect(0, 0, page_w, band_h, "F")

    # ── Logo icon (logo-white.png, ~31×41px → render at ~9×12 mm) ────
    logo_buf = io.BytesIO(_logo_bytes())
    logo_w, logo_h = 8.0, 10.5   # mm, preserves 31:41 aspect ratio
    logo_x = 10.0
    logo_y = (band_h - logo_h) / 2
    try:
        pdf.image(logo_buf, x=logo_x, y=logo_y, w=logo_w, h=logo_h, type="PNG")
    except Exception:
        pass  # never break PDF generation over a missing logo

    # ── "FOID" wordmark beside the icon ──────────────────────────────
    text_x = logo_x + logo_w + 3.0
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(text_x, 5.0)
    pdf.cell(0, 8, "FOID", ln=False)

    # ── Separator dot ─────────────────────────────────────────────────
    sep_x = text_x + pdf.get_string_width("FOID") + 3.0
    pdf.set_font("Helvetica", "", 13)
    pdf.set_xy(sep_x, 5.0)
    pdf.cell(0, 8, "·", ln=False)

    # ── Document title ────────────────────────────────────────────────
    title_x = sep_x + pdf.get_string_width("· ") + 1.0
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(title_x, 5.0)
    pdf.cell(0, 8, title, ln=False)

    # ── Subtitle line (right-aligned) ─────────────────────────────────
    if subtitle:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(10.0, 16.5)
        pdf.cell(page_w - 20.0, 6, subtitle, ln=False, align="R")

    # ── Reset text colour for document body ───────────────────────────
    pdf.set_text_color(30, 30, 30)

    return band_h
