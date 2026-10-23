"""Bachs payment service — checkout session creation and webhook verification.

Docs:
  https://docs.bachs.io/api-reference/payments/create-checkout-session
  https://docs.bachs.io/guides/webhooks/overview
  https://docs.bachs.io/guides/webhooks/events/collection-succeeded

Usage flow:
  1. create_checkout_session()  →  returns checkout_url to redirect user to
  2. User pays on Bachs hosted page
  3. Bachs fires POST to your webhook endpoint with event type "collection.succeeded"
  4. verify_webhook_signature()  →  must return True before processing
  5. Extract data.reference  →  look up pending WalletTransaction
  6. Credit paid_credits

Sandbox vs production is controlled by BACHS_API_KEY prefix:
  sk_sandbox_...  →  sandbox base URL
  sk_live_...     →  production base URL
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from ..config import get_settings

_SANDBOX_BASE = "https://sandbox-api.bachs.io"
_PRODUCTION_BASE = "https://api.bachs.io"
_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def _base_url() -> str:
    key = get_settings().BACHS_API_KEY
    return _SANDBOX_BASE if key.startswith("sk_sandbox_") else _PRODUCTION_BASE


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().BACHS_API_KEY}",
        "Content-Type": "application/json",
    }


async def create_checkout_session(
    *,
    amount_ngn: int,
    email: str,
    name: str,
    reference: str,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Initialise a Bachs checkout session for a raw NGN amount.

    Uses the `pricing` field (raw amount, no product catalog required).
    Returns the full Bachs response including `checkout_url`.

    Raises httpx.HTTPStatusError on non-2xx from Bachs.
    """
    body: dict[str, object] = {
        "pricing": {
            "currency": "NGN",
            "amount": f"{amount_ngn:.2f}",
        },
        "customer": {
            "email": email,
            "name": name,
        },
        "reference": reference,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "payment_method_types": ["NGN_BANK_TRANSFER"],
        "expires_in_minutes": 60,
    }
    if metadata:
        body["metadata"] = metadata

    async with httpx.AsyncClient(base_url=_base_url(), timeout=_TIMEOUT) as client:
        r = await client.post(
            "/v1/checkout-sessions",
            json=body,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


def verify_webhook_signature(
    payload: bytes,
    timestamp: str,
    signature_v2: str,
) -> bool:
    """Verify a Bachs webhook using X-Bachs-Signature-V2 (preferred).

    X-Bachs-Signature-V2 format:  t={timestamp},v1={hex_signature}

    The signed string is:  "{timestamp}.{raw_body}"
    Algorithm: HMAC-SHA256 using BACHS_WEBHOOK_SECRET as the key.

    Returns True if the signature is valid, False otherwise.
    Never raises — signature failures are non-fatal caller-side rejections.
    """
    try:
        secret = get_settings().BACHS_WEBHOOK_SECRET.encode()

        # Parse v2 header: "t=1234567890,v1=abc123..."
        parts = dict(item.split("=", 1) for item in signature_v2.split(","))
        ts = parts.get("t", timestamp)       # fall back to separate timestamp header
        sig = parts.get("v1", "")

        if not sig:
            return False

        signed_payload = f"{ts}.{payload.decode()}".encode()
        expected = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
