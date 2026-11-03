# Python SDK — `foid`

A server-side SDK for Python ≥ 3.10. It covers the Continue with FOID code exchange (client secret or key pair), the Open API, webhook signature verification and PKCE helpers. It's synchronous (built on `httpx`) and holds secrets, so **never ship it to a client**.

```bash
pip install "./sdks/python[keypair]"   # see SDKs → Install; not on PyPI yet
```

The `keypair` extra adds `cryptography`, needed only for key pairs and `python -m foid keygen`.

## Quick start

```python
import os
from foid import Foid, FoidError

foid = Foid(
    api_key=os.environ["FOID_API_KEY"],              # Open API
    client_id=os.environ["FOID_CLIENT_ID"],          # Continue with FOID
    client_secret=os.environ["FOID_CLIENT_SECRET"],
)

# Continue with FOID: the code + verifier from your front end
person = foid.oauth.exchange(code, code_verifier)
print(person["subject_id"], person["subject"]["first_name"])

# Open API
result = foid.check_nin(number="12345678901", first_name="Ada", last_name="Obi",
                        consent={"obtained": True, "purpose": "Account opening"})
```

## `Foid`

```python
Foid(*, api_key=None, client_id=None, client_secret=None, private_key_pem=None,
     key_id=None, base_url="https://api.foid.ng", timeout=15.0)
```

All arguments are keyword-only. Pass only the credentials you use.

| Argument | Used for |
|---|---|
| `api_key` | The Open API (`request()` and the helpers). `FOID_TEST_…` / `FOID_LIVE_…`. |
| `client_id` | `oauth.exchange()`: your sign-in app's client ID. |
| `client_secret` | `oauth.exchange()` for client-secret apps. |
| `private_key_pem` | `oauth.exchange()` for key-pair apps. If set, it's used instead of `client_secret`. |
| `key_id` | Optional `kid` put in the assertion header (the `kid` from your public JWK). |
| `base_url` | The FOID API host, e.g. `http://localhost:8000` when running FOID locally. A trailing `/` is ignored. |
| `timeout` | HTTP timeout in seconds. |

The client keeps one `httpx.Client` open. Close it with `foid.close()`, or use it as a context manager:

```python
with Foid(api_key=key) as foid:
    foid.request("GET", "/ping")
```

### `foid.oauth.exchange(code, code_verifier, redirect_uri=None)`

Exchanges the one-time code from the sign-in popup for the person's result. Calls `POST /api/open/v1/oauth/token`. Do it **once, within 60 seconds**.

- With `client_secret`: sends HTTP Basic `client_id:client_secret`.
- With `private_key_pem`: sends a signed `client_assertion` (ES256, valid 60 seconds, `aud` = the token URL).
- `redirect_uri` is required only in redirect mode, and must be the exact URI used to start sign-in.

Returns the result dict (`object: "foid_sign_in"`, `subject_id`, `subject`, `scopes`, `checks`, `foid_account`, `face_rematched_at`, `nonce`, `sandbox`, `env`). See [the result](/guide/continue-with-foid#the-result).

Raises:

- `ValueError` if `client_id` is missing, or there's neither `client_secret` nor `private_key_pem`.
- `FoidError` from the token endpoint, with `code` set to the OAuth error: `invalid_grant` (expired, used, wrong verifier) or `invalid_client` (wrong secret or assertion).

```python
try:
    person = foid.oauth.exchange(code, code_verifier)
except FoidError as e:
    if e.code == "invalid_grant":
        ...   # ask the person to sign in again
```

### `foid.request(method, path, *, json=None, params=None, idempotency_key=None)`

Calls any Open API endpoint with your API key. `path` is relative to `/api/open/v1`, e.g. `"/subjects"`.

- `json`: the request body. `params`: query parameters. `idempotency_key`: sent as the `Idempotency-Key` header.
- Returns the parsed JSON, or `None` for an empty response (e.g. `204` from `DELETE`).
- Raises `ValueError` if `api_key` isn't set, and `FoidError` for any `4xx` / `5xx`.

```python
foid.request("GET", "/verifications", params={"status": "pending"})
foid.request("POST", f"/verifications/{vid}/cancel")
foid.request("GET", f"/subjects/{sid}/trust-report")
foid.request("DELETE", f"/subjects/{sid}")                       # None
foid.request("POST", "/checks/nin", json=body, idempotency_key="chk-cust_1001")
```

### Open API helpers

Shortcuts for `request()`. Keyword arguments become the JSON body.

| Method | Calls |
|---|---|
| `get_subject(subject_id)` | `GET /subjects/{id}` |
| `create_verification(**body)` | `POST /verifications`. Pass `idempotency_key=` to send the header; it isn't part of the body. |
| `get_verification(verification_id)` | `GET /verifications/{id}` |
| `check_nin(**body)` | `POST /checks/nin` |
| `check_bvn(**body)` | `POST /checks/bvn` |

```python
v = foid.create_verification(checks=["nin", "liveness"], purpose="Open a wallet",
                             customer_ref="cust_1001", first_name="Ada", last_name="Obi",
                             return_url="https://acme.example/kyc/done",
                             idempotency_key="onboard-cust_1001")
print(v["hosted_url"])
```

Field details: [Hosted verification](/guide/hosted-verification), [NIN and BVN checks](/guide/checks), [API reference](/api/reference).

### `foid.webhooks.verify(payload, header, secret, tolerance=300)`

The same as the module-level [`verify_webhook`](#verify-webhook).

## `verify_webhook(payload, header, secret, tolerance=300)` {#verify-webhook}

```python
from foid import verify_webhook, WebhookError

event = verify_webhook(raw_body, request.headers.get("FOID-Signature", ""), "whsec_…")
```

Checks the `FOID-Signature` header (`t=…,v1=…`) against the **raw** body (`bytes` or `str`) and returns the parsed event dict. Raises `WebhookError` if the header is missing or malformed, the timestamp is more than `tolerance` seconds away from now, or no `v1` signature matches. See [Webhooks](/guide/webhooks#verify-the-signature).

## `create_pkce()`

```python
from foid import create_pkce
p = create_pkce()   # {"code_verifier", "code_challenge", "state", "nonce"}
```

For servers that start the sign-in themselves (server-led PKCE). Keep `code_verifier`, `state` and `nonce` on the server; put `code_challenge` (S256), `state` and `nonce` in the authorize URL. See [Server-led sign-in](/guide/continue-with-foid#server-led-sign-in).

## Key pairs — `foid.keypair`

Needs the `keypair` extra.

| Function | Returns |
|---|---|
| `generate_keypair()` | `(private_key_pem, public_jwk)`: a new EC P-256 key. Keep the PEM secret; paste the JWK (with a random `kid`) into the console. |
| `client_assertion(private_key_pem, client_id, audience, kid=None)` | The signed ES256 JWT that `oauth.exchange` sends (`iss` = `sub` = client ID, `aud` = audience, 60-second expiry, random `jti`). You rarely need it directly. |

From the command line:

```bash
python -m foid keygen
```

This writes `foid_private_key.pem` in the current directory (refusing to overwrite an existing one) and prints the public JWK to paste into **Sign-in apps → Edit → Key pair**. Then:

```python
foid = Foid(client_id="foid_app_live_…", private_key_pem=open("foid_private_key.pem").read(), key_id="<kid>")
```

## Errors

### `FoidError`

Raised for any non-2xx response.

| Attribute | |
|---|---|
| `status` | HTTP status |
| `code` | The Open API `error.code` (e.g. `consent_revoked`), the OAuth `error` for the token endpoint (e.g. `invalid_grant`), or `http_error` when the body has neither (e.g. `422` validation errors, `429`) |
| `message` | Human-readable message |
| `body` | The parsed response body, when it was JSON |

```python
try:
    foid.get_subject(sid)
except FoidError as e:
    if e.code == "consent_revoked":
        ...   # stop using and delete this person's data
    elif e.status == 422:
        print(e.body["detail"])
```

Network failures and timeouts surface as `httpx` exceptions (`httpx.HTTPError`). Missing credentials raise `ValueError`.

### `WebhookError`

Raised by `verify_webhook` / `webhooks.verify` when a signature can't be verified.

## Reference

| Name | Kind |
|---|---|
| `Foid` | client class |
| `FoidError`, `WebhookError` | exceptions |
| `create_pkce` | function |
| `verify_webhook` | function |
| `foid.keypair.generate_keypair`, `foid.keypair.client_assertion` | functions (`keypair` extra) |
| `foid.__version__` | `"0.1.0"` |
