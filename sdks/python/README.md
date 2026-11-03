# foid — FOID Python SDK

Server-side SDK for FOID: the **Continue with FOID** code exchange (client secret or key pair), the **Open API** (checks, hosted verifications, subjects) and **webhook signature** verification.

- Python ≥ 3.10, synchronous, built on `httpx`.
- Holds your secrets: use it only on your server.

## Install

Not on PyPI yet. Install from the FOID repository:

```bash
pip install "./sdks/python[keypair]"
# uv:  uv add ./sdks/python --extra keypair
```

The `keypair` extra adds `cryptography`. It's needed only for key-pair apps (`private_key_jwt`) and `python -m foid keygen`.

## Quick start

```python
import os
from foid import Foid, FoidError

foid = Foid(
    api_key=os.environ["FOID_API_KEY"],               # Open API: FOID_TEST_… / FOID_LIVE_…
    client_id=os.environ["FOID_CLIENT_ID"],           # Continue with FOID: foid_app_…
    client_secret=os.environ["FOID_CLIENT_SECRET"],   # foid_cs_…
    # base_url="http://localhost:8000",               # when running FOID yourself
)
```

### Continue with FOID

Your front end (e.g. `@foid/react`) sends you `code` and `codeVerifier`. Exchange them once, within 60 seconds:

```python
person = foid.oauth.exchange(code, code_verifier)
person["subject_id"]               # stable ID for this person at your business
person["subject"]["first_name"]    # plus whatever scopes they approved
```

### Open API

```python
result = foid.check_nin(
    number="12345678901", first_name="Ada", last_name="Obi",
    consent={"obtained": True, "purpose": "Account opening"},
)

v = foid.create_verification(
    checks=["nin", "liveness"], purpose="Open a wallet", customer_ref="cust_1001",
    return_url="https://acme.example/kyc/done", idempotency_key="onboard-cust_1001",
)
print(v["hosted_url"])   # send the person here

foid.get_verification(v["id"])
foid.get_subject(result["subject_id"])
foid.request("DELETE", f"/subjects/{result['subject_id']}")   # any endpoint
```

### Webhooks

```python
from foid import verify_webhook, WebhookError

event = verify_webhook(raw_body, request.headers["FOID-Signature"], os.environ["FOID_WEBHOOK_SECRET"])
```

### Key pair instead of a client secret

```bash
python -m foid keygen    # writes foid_private_key.pem, prints the public JWK for the console
```

```python
foid = Foid(client_id="foid_app_live_…", private_key_pem=open("foid_private_key.pem").read())
```

## API

| | |
|---|---|
| `Foid(api_key=, client_id=, client_secret=, private_key_pem=, key_id=, base_url=, timeout=)` | Client. Also a context manager; `close()` releases the connection. |
| `foid.oauth.exchange(code, code_verifier, redirect_uri=None)` | Continue with FOID code → result |
| `foid.request(method, path, json=, params=, idempotency_key=)` | Any Open API call (path relative to `/api/open/v1`) |
| `foid.get_subject(id)`, `create_verification(**body)`, `get_verification(id)`, `check_nin(**body)`, `check_bvn(**body)` | Helpers |
| `foid.webhooks.verify(...)` / `verify_webhook(payload, header, secret, tolerance=300)` | Webhook signature check → event |
| `create_pkce()` | `{code_verifier, code_challenge, state, nonce}` for server-led sign-in |
| `foid.keypair.generate_keypair()`, `foid.keypair.client_assertion(...)` | Key pairs (`keypair` extra) |
| `FoidError` (`status`, `code`, `message`, `body`), `WebhookError` | Errors |

## Security

- Keep the API key, client secret and private key on your server, in environment variables or a secret manager.
- Exchange each code once. A second exchange revokes the grant.
- Verify webhooks against the raw body.

## Docs

Full reference: the FOID docs site, page **SDKs → Python** (`docs/sdks/python.md`; run `cd docs && pnpm dev` for http://localhost:5177/sdks/python). Guides: Continue with FOID, Hosted verification, Webhooks. Working example: `demo/` (Harbor).
