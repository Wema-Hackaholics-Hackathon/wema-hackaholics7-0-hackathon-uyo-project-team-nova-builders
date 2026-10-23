"""Bank logo resolution service.

Fetches the full institution list from https://nigerianbanks.xyz on first use
and caches it for 24 hours.  No hardcoded maps.

Resolution priority:
  1. Mono CDN  — cdn.mono.co/institutions/{id}.png  (production; sandbox omits id)
  2. nigerianbanks.xyz matched by CBN bank code
  3. nigerianbanks.xyz matched by full normalised institution name
  4. nigerianbanks.xyz matched by any significant token in the institution name
     (handles Mono returning short aliases like "Opay" for
      "OPay Digital Services Limited (OPay)")
  5. None  — frontend falls back to the bank-name initial avatar
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

_MONO_CDN = "https://cdn.mono.co/institutions/{institution_id}.png"
_NBX_URL = "https://nigerianbanks.xyz"
_CACHE_TTL = 86_400  # 24 hours

# Short generic words that appear in many bank names — skip as tokens
# to avoid false matches (e.g. "bank" matching every institution).
_STOP_TOKENS = frozenset(
    "bank mfb ng microfinance limited ltd plc nigeria nigerian "
    "digital services holdings holding company trust mortgage finance".split()
)

# Abbreviation → canonical search term fed into the name index.
# Only needed for aliases where the full name is completely different.
_ALIASES: dict[str, str] = {
    "gtbank":     "guaranty trust bank",
    "gtco":       "guaranty trust bank",
    "uba":        "united bank for africa",
    "fcmb":       "first city monument bank",
    "ecobank":    "ecobank nigeria",
    "first bank": "first bank of nigeria",
    "firstbank":  "first bank of nigeria",
}


class _Institution(TypedDict):
    name: str
    slug: str
    code: str
    logo: str


# ── In-process cache ────────────────────────────────────────────────────────
_cache_lock = asyncio.Lock()
_by_code: dict[str, str] = {}    # bank_code (stripped)  → logo URL
_by_name: dict[str, str] = {}    # full normalised name   → logo URL
_by_token: dict[str, str] = {}   # significant token      → logo URL (shorter name wins)
_loaded_at: float = -_CACHE_TTL  # sentinel: forces load on first call


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.strip().lower())).strip()


def _tokens(normalised_name: str) -> list[str]:
    """Return significant (non-stop, ≥4-char) words from a normalised name."""
    return [w for w in normalised_name.split() if len(w) >= 4 and w not in _STOP_TOKENS]


async def _load_institutions() -> None:
    """Fetch nigerianbanks.xyz and rebuild the in-process indexes."""
    global _by_code, _by_name, _by_token, _loaded_at
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(_NBX_URL, headers={"Accept": "application/json"})
            r.raise_for_status()
            institutions: list[_Institution] = r.json()

        by_code: dict[str, str] = {}
        by_name: dict[str, str] = {}
        # token → (logo, name_length) — shorter registered name wins on collision
        # so "Kuda Bank" beats "Kuda Microfinance Bank" for the token "kuda"
        token_best: dict[str, tuple[str, int]] = {}

        for inst in institutions:
            logo: str = inst.get("logo", "")
            if not logo:
                continue

            # bank code index
            code: str = (inst.get("code") or "").strip()
            if code:
                by_code[code] = logo

            # full-name index
            norm = _normalise(inst.get("name", ""))
            if norm:
                by_name[norm] = logo

            # token index — keep the entry whose registered name is shortest
            for token in _tokens(norm):
                existing = token_best.get(token)
                if existing is None or len(norm) < existing[1]:
                    token_best[token] = (logo, len(norm))

        _by_code = by_code
        _by_name = by_name
        _by_token = {tok: val[0] for tok, val in token_best.items()}
        _loaded_at = time.monotonic()
        logger.info("bank_logo_service: loaded %d institutions", len(institutions))

    except Exception:
        logger.warning(
            "bank_logo_service: failed to fetch institutions — logos unavailable",
            exc_info=True,
        )


async def _ensure_loaded() -> None:
    """Load (or refresh) the institution index if the cache has expired."""
    if time.monotonic() - _loaded_at < _CACHE_TTL:
        return
    async with _cache_lock:
        # Re-check inside the lock to avoid double fetches
        if time.monotonic() - _loaded_at < _CACHE_TTL:
            return
        await _load_institutions()


async def resolve_logo(
    *,
    institution_id: str | None = None,
    bank_code: str | None = None,
    institution_name: str | None = None,
) -> str | None:
    """Return the best available logo URL for a bank, or None.

    Args:
        institution_id:   Mono institution ID (production only).
        bank_code:        CBN bank code from the Mono institution object.
        institution_name: Bank name string from Mono.
    """
    # 1. Mono CDN — only available in production (sandbox omits institution_id)
    if institution_id:
        return _MONO_CDN.format(institution_id=institution_id)

    await _ensure_loaded()

    # 2. Match by CBN bank code
    if bank_code:
        logo = _by_code.get(bank_code.strip())
        if logo:
            return logo

    # 3. Match by full normalised institution name
    if institution_name:
        norm = _normalise(institution_name)

        # 3a. Direct full-name match
        logo = _by_name.get(norm)
        if logo:
            return logo

        # 3b. Known abbreviation → expand to canonical name and retry
        canonical = _ALIASES.get(norm)
        if canonical:
            logo = _by_name.get(canonical)
            if logo:
                return logo

        # 4. Token match — handles short aliases like "Opay" whose registered
        #    name ("OPay Digital Services Limited") shares a significant token
        for token in _tokens(norm):
            logo = _by_token.get(token)
            if logo:
                return logo

    return None
