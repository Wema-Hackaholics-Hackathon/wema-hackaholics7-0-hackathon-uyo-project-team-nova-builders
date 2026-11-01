"""NIN / BVN identity lookups behind a provider interface.

get_provider(env) returns the adapter for an environment:
  test → MockProvider always (sandbox magic numbers, never billed)
  live → settings.IDENTITY_PROVIDER; "mock" in live raises ProviderUnavailable,
         so live keys never get fake results.

Adding a real provider (Dojah, Prembly, Youverify, QoreID, Smile ID, Mono
Lookup, …): implement IdentityProvider.lookup_nin / lookup_bvn returning an
IdentityRecord, and register it in _LIVE_PROVIDERS.
"""

from __future__ import annotations

from app.config import get_settings

from .base import IdentityProvider, IdentityRecord, ProviderUnavailable
from .mock import MockProvider

_LIVE_PROVIDERS: dict[str, type[IdentityProvider]] = {}


def get_provider(env: str) -> IdentityProvider:
    if env == "test":
        return MockProvider()
    name = get_settings().IDENTITY_PROVIDER
    cls = _LIVE_PROVIDERS.get(name)
    if cls is None:
        raise ProviderUnavailable(
            "No live identity provider is configured — use test keys, or configure a provider"
        )
    return cls()


__all__ = ["IdentityProvider", "IdentityRecord", "ProviderUnavailable", "get_provider"]
