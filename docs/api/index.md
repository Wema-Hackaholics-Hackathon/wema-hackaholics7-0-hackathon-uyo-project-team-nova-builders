# API overview

The FOID Open API is a JSON-over-HTTPS API for your **server**. Never call it from a browser or mobile app — that would expose your API key. For the browser side, use the [React SDK](/sdks/react) or the [hosted verification](/guide/hosted-verification) page.

Every endpoint, with real example responses: **[Endpoints →](./reference)**

## Base URL

| | |
|---|---|
| Production | `https://api.foid.ng/api/open/v1` |
| Local (running FOID yourself) | `http://localhost:8000/api/open/v1` |

## Authentication

Send your API key as a bearer token:

```http
GET /api/open/v1/ping
Authorization: Bearer FOID_TEST_…
```

| Key | Environment | What it does |
|---|---|---|
| `FOID_TEST_…` | Test | Sandbox: every check passes with dummy data, never billed. |
| `FOID_LIVE_…` | Live | Real lookups, billed. Only after FOID approves your business (KYB). |

Create keys in the console under **API keys**. A key is shown **once** — FOID stores only a hash. If your business has an **IP allow-list**, live keys only work from those addresses (`403 ip_not_allowed`).

The one exception is the [token endpoint](./reference#post-oauth-token) for Continue with FOID, which uses your **sign-in app's** client ID + client secret (or a key pair), not the API key. See [Keys and credentials](/guide/concepts#keys-and-credentials).

## Requests and responses

- Send JSON with `Content-Type: application/json` (the document check uses `multipart/form-data`).
- IDs are opaque strings; store them as text.
- Timestamps are ISO 8601 in UTC, e.g. `2026-11-03T20:25:02.091651+00:00`.
- Fields you didn't send and don't apply come back as `null`.
- Lists return `{"object": "list", "data": [...]}`. Use `limit` (max 100) and `offset` where supported.
- Every response carries a **`FOID-Request-Id`** header. Quote it when you contact support; the same ID appears in the console under **Request logs**.

## Errors

Errors have one shape:

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

| HTTP | `type` | Typical `code`s |
|---|---|---|
| 400 | `invalid_request` | `consent_required`, `unsupported_file_type` |
| 401 | `authentication` | missing, wrong or revoked API key |
| 403 | `permission` | `consent_revoked`, `scope_not_granted`, `ip_not_allowed` |
| 404 | `not_found` | `subject_not_found`, `verification_not_found` |
| 409 | `conflict` | `verification_closed`, `idempotency_key_reused`, `no_face_on_file`, `no_foid_account` |
| 502 / 503 | `provider` | an identity provider is down — retry later |

Branch on `code`, not on `message` (messages are for humans and may change). `param` names the field at fault when there is one. More in [Errors, limits, idempotency](/guide/errors).

Two responses don't use this shape yet:

- **`422` — the request body didn't validate** (missing field, wrong type, bad format). The body lists every problem:
  `{"detail": [{"loc": ["body", "number"], "msg": "Field required", "type": "missing"}]}`
- **`429` — rate limited:** `{"error": "Rate limit exceeded: 120 per 1 minute"}`. Back off and retry.

The token endpoint is different: it uses OAuth's standard error format, `{"error": "invalid_grant", "error_description": "…"}`.

## Idempotency

`POST /verifications`, `POST /checks/nin` and `POST /checks/bvn` accept an **`Idempotency-Key`** header. Send the same key with the same body and you get the original response back (with `Idempotent-Replayed: true`) instead of a second verification or a second billed check. The same key with a *different* body is refused with `409 idempotency_key_reused`. Keys are remembered for 24 hours.

```http
POST /api/open/v1/verifications
Authorization: Bearer FOID_TEST_…
Idempotency-Key: onboard-cust_1001
```

## Rate limits

120 requests per minute per API key on the verification and check endpoints; 60 per minute on the token endpoint. Over the limit you get `429` — wait and retry with backoff.

## Versioning

The version is in the path (`/v1`). Within `v1` we only make additive changes: new endpoints, new optional fields, new event types and new error codes. Write your code to ignore fields it doesn't know. Breaking changes would ship as `/v2`. Changes are listed in the [changelog](/changelog).
