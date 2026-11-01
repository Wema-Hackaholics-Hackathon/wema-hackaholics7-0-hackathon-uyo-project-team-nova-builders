"""Provider interface + name matching shared by all identity adapters."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol


class ProviderUnavailable(Exception):
    """The provider is not configured or is down — the check result is `error`, not `failed`."""


@dataclass
class IdentityRecord:
    found: bool
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None   # YYYY-MM-DD
    phone: str | None = None
    gender: str | None = None
    provider_ref: str | None = None


class IdentityProvider(Protocol):
    name: str

    async def lookup_nin(self, nin: str) -> IdentityRecord: ...
    async def lookup_bvn(self, bvn: str) -> IdentityRecord: ...


# ---------------------------------------------------------------------------
# Name / DOB matching
# ---------------------------------------------------------------------------

def _tokens(*parts: str | None) -> set[str]:
    text = " ".join(p for p in parts if p)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {t for t in re.split(r"[^a-z]+", text) if len(t) > 1}


@dataclass
class MatchResult:
    name_match: bool
    name_score: float          # share of the supplied name tokens found on the record
    dob_match: bool | None     # None when either side has no DOB


def match_record(
    record: IdentityRecord,
    first_name: str | None,
    last_name: str | None,
    middle_name: str | None = None,
    date_of_birth: str | None = None,
) -> MatchResult:
    """First and last name must both appear on the record (any order); middle name is a bonus."""
    on_record = _tokens(record.first_name, record.middle_name, record.last_name)
    supplied = _tokens(first_name, middle_name, last_name)
    required = _tokens(first_name) | _tokens(last_name)
    score = len(supplied & on_record) / len(supplied) if supplied else 0.0
    name_match = bool(required) and required <= on_record
    dob_match = None
    if date_of_birth and record.date_of_birth:
        dob_match = date_of_birth.strip() == record.date_of_birth.strip()
    return MatchResult(name_match=name_match, name_score=round(score, 2), dob_match=dob_match)
