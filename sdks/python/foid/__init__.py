"""FOID server SDK.

    from foid import Foid
    foid = Foid(client_id="foid_app_test_…", client_secret="foid_cs_test_…", api_key="FOID_TEST_…")
    person = foid.oauth.exchange(code, code_verifier)        # Continue with FOID
    foid.webhooks.verify(raw_body, request.headers["FOID-Signature"], "whsec_…")
"""

from .client import Foid, FoidError
from .pkce import create_pkce
from .webhooks import WebhookError, verify_webhook

__all__ = ["Foid", "FoidError", "WebhookError", "create_pkce", "verify_webhook"]
__version__ = "0.1.0"
