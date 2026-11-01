"""Sandbox identity provider — deterministic magic numbers, used for all test-mode keys.

Last digit of the NIN/BVN decides the outcome:
  …0 – …7  found; the record echoes the name the caller supplied (so it matches)
  …8       found, but under a different name  → name mismatch
  …9       not found
"""

from __future__ import annotations

from .base import IdentityRecord

SANDBOX_NAME = ("Chidinma", "Ada", "Okafor")


class MockProvider:
    name = "mock"

    def __init__(self) -> None:
        self._echo: tuple[str | None, str | None, str | None] = (None, None, None)
        self._dob: str | None = None

    def expect(
        self,
        first_name: str | None,
        middle_name: str | None,
        last_name: str | None,
        date_of_birth: str | None = None,
    ) -> "MockProvider":
        """Tell the sandbox which name/DOB to echo back for 'found' numbers."""
        self._echo = (first_name, middle_name, last_name)
        self._dob = date_of_birth
        return self

    def _record(self, number: str) -> IdentityRecord:
        last = number[-1]
        if last == "9":
            return IdentityRecord(found=False)
        if last == "8" or not any(self._echo):
            first, middle, surname = SANDBOX_NAME
        else:
            first, middle, surname = self._echo
        return IdentityRecord(
            found=True,
            first_name=first,
            middle_name=middle,
            last_name=surname,
            date_of_birth=self._dob or "1995-04-12",
            gender="F",
            provider_ref=f"mock_{number[-4:]}",
        )

    async def lookup_nin(self, nin: str) -> IdentityRecord:
        return self._record(nin)

    async def lookup_bvn(self, bvn: str) -> IdentityRecord:
        return self._record(bvn)
