# Errors, limits, idempotency

## Error shape

Open API errors look like this:

```json
{
  "error": {
    "type": "permission",
    "code": "consent_revoked",
    "message": "The person has revoked this business's access to their data",
    "param": null
  }
}
```

- **`code`** is stable. Branch on it.
- **`message`** is for humans and may change.
- **`param`** names the field at fault, when there is one.
- **`type`** groups codes by HTTP status: `invalid_request` (400/413/422), `authentication` (401), `permission` (403), `not_found` (404), `conflict` (409), `gone` (410), `rate_limit` (429), `provider` (502/503).

Two responses use a different shape:

- **`422` validation errors** (missing field, wrong type, bad format) come back as a list:
  ```json
  { "detail": [{ "type": "missing", "loc": ["body", "consent"], "msg": "Field required" }] }
  ```
- **`429` rate limit:** `{"error": "Rate limit exceeded: 120 per 1 minute"}`.

The [token endpoint](/api/reference#post-oauth-token) uses OAuth's format instead: `{"error": "invalid_grant", "error_description": "…"}`. See [Continue with FOID: errors](./continue-with-foid#errors).

In the SDKs, every non-2xx response raises `FoidError` with `status`, `code`, `message` (Python) or `description` (Node), and the parsed `body`. For the two shapes above, `code` is `http_error` and the details are in `body`.

## Error codes

| HTTP | `code` | Meaning | What to do |
|---|---|---|---|
| 400 | `invalid_nin`, `invalid_bvn` | The number isn't exactly 11 digits | Fix the input |
| 400 | `consent_required` | Document check sent without `consent_obtained=true` | Collect and send consent |
| 400 | `unsupported_file_type` | Document isn't JPEG, PNG or WebP | Re-upload |
| 400 | `invalid_webhook_url` | The webhook URL isn't allowed. See [allowed URLs](./webhooks#allowed-urls). | Use a public https URL |
| 401 | `missing_api_key` | No `Authorization: Bearer …` header | Send the key |
| 401 | `invalid_api_key` | Unknown, malformed or revoked key | Check which key you deployed |
| 403 | `live_mode_disabled` | Live mode isn't enabled yet (KYB) | Use a test key, or [go live](./going-live) |
| 403 | `ip_not_allowed` | Live key used from an IP outside your allow-list | Call from an allow-listed server |
| 403 | `organisation_suspended` | The organisation isn't active | Contact FOID |
| 403 | `consent_revoked` | The person revoked your access | Stop and delete, see [revocation](./subjects#when-a-person-revokes-consent) |
| 403 | `scope_not_granted` | You don't hold the scope this read needs | Ask for it in a new verification or sign-in |
| 404 | `subject_not_found` | No such subject in this environment | Check the ID and the key's environment |
| 404 | `verification_not_found` | No such verification in this environment | Check the ID and the key's environment |
| 404 | `credential_not_found` | The person has no FOID credential yet (trust report) | — |
| 409 | `verification_closed` | The verification is already completed or cancelled | — |
| 409 | `idempotency_key_reused` | Same `Idempotency-Key`, different request body | Use a new key per distinct request |
| 409 | `no_face_on_file` | `reverify` for a subject without an earlier liveness face | Use `liveness` first |
| 409 | `no_foid_account` | Trust report for someone without a FOID account | — |
| 413 | `file_too_large` | Document image over 8 MB | Re-upload smaller |
| 422 | (validation) | Body failed validation. See `detail`. | Fix the request |
| 429 | (rate limit) | Too many requests | Back off and retry |

The hosted page and the sign-in popup show their own errors to the person (for example `too_many_attempts` after 3 tries on one step, or `verification_expired`). Your server sees the outcome on the verification instead.

## Idempotency {#idempotency}

Network retries shouldn't create a second verification or pay for a second check. `POST /verifications`, `POST /checks/nin` and `POST /checks/bvn` accept an **`Idempotency-Key`** header:

- Same key + same body: you get the **original response** back, with the header `Idempotent-Replayed: true`. Nothing new is created or billed.
- Same key + different body: `409 idempotency_key_reused`.
- Keys are remembered for 24 hours, per organisation and environment.

Use something unique to the action, such as `onboard-<your user id>` or a UUID you store with the request.

::: code-group

```bash [curl]
curl https://foid-iy7u.onrender.com/api/open/v1/verifications \
  -H "Authorization: Bearer $FOID_API_KEY" \
  -H "Idempotency-Key: onboard-cust_1001" \
  -H "Content-Type: application/json" \
  -d '{"checks": ["nin"], "purpose": "Open a wallet", "customer_ref": "cust_1001"}'
```

```python [Python]
v = foid.create_verification(checks=["nin"], purpose="Open a wallet", customer_ref="cust_1001",
                             idempotency_key="onboard-cust_1001")
```

```js [Node]
const v = await foid.createVerification({ checks: ['nin'], purpose: 'Open a wallet', customer_ref: 'cust_1001',
  idempotencyKey: 'onboard-cust_1001' })
```

:::

The SDKs' `check_nin` / `checkNin` don't take an idempotency key. For idempotent checks, call `request("POST", "/checks/nin", json=…, idempotency_key=…)` (Python) or `request('POST', '/checks/nin', { json, idempotencyKey })` (Node).

## Rate limits

| Endpoints | Limit |
|---|---|
| `POST /verifications`, `POST /checks/nin`, `POST /checks/bvn` | 120 requests per minute per API key |
| `POST /checks/nin-document` | 30 per minute |
| `POST /oauth/token` | 60 per minute |

Over the limit you get `429`. Wait and retry with exponential backoff.

## Request IDs

Every Open API response has a **`FOID-Request-Id`** header. The same ID appears in the console under **Request logs**. Log it with your own request, and quote it when you contact support.
