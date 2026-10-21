"""Paystack payment service.

Handles:
- Transaction initialisation (checkout URL)
- Transaction verification
- Webhook HMAC-SHA512 signature verification

All methods read PAYSTACK_SECRET_KEY from settings.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from ..config import get_settings

_BASE = "https://api.paystack.co"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


async def initialize_transaction(
    *,
    email: str,
    amount_kobo: int,
    metadata: dict[str, object],
    reference: str,
    callback_url: str | None = None,
) -> dict[str, object]:
    """Initialise a Paystack payment. Returns Paystack's response including authorization_url."""
    body: dict[str, object] = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "metadata": metadata,
    }
    if callback_url:
        body["callback_url"] = callback_url
    async with httpx.AsyncClient(base_url=_BASE) as client:
        r = await client.post(
            "/transaction/initialize",
            json=body,
            headers=_headers(),
        )
        _ = r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


async def verify_transaction(reference: str) -> dict[str, object]:
    """Verify a Paystack transaction by reference. Returns the transaction object."""
    async with httpx.AsyncClient(base_url=_BASE) as client:
        r = await client.get(
            f"/transaction/verify/{reference}",
            headers=_headers(),
        )
        _ = r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Paystack webhook HMAC-SHA512 signature.

    Paystack sends the signature in the X-Paystack-Signature header.
    Returns True if valid, False otherwise.
    """
    secret = get_settings().PAYSTACK_SECRET_KEY.encode()
    expected = hmac.new(secret, payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
