"""Verify FOID webhook signatures.  Header:  FOID-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "t.body")>"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


class WebhookError(Exception):
    pass


def verify_webhook(payload: bytes | str, header: str, secret: str, tolerance: int = 300) -> dict[str, Any]:
    """The parsed event, or WebhookError. Use the RAW request body, not re-serialised JSON."""
    body = payload.encode() if isinstance(payload, str) else payload
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    try:
        t = int(parts["t"])
    except (KeyError, ValueError):
        raise WebhookError("Missing or malformed FOID-Signature header")
    if abs(time.time() - t) > tolerance:
        raise WebhookError("Webhook timestamp is outside the tolerance (possible replay)")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    sigs = [v for k, v in (p.split("=", 1) for p in header.split(",") if "=" in p) if k == "v1"]
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise WebhookError("Webhook signature doesn't match")
    return json.loads(body)
