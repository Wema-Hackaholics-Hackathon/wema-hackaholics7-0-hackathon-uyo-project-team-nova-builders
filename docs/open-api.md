# FOID Open API — developer guide

Verify your customers' identity with FOID: **NIN**, **BVN** and a **branded liveness check** — through
a FOID-hosted page you redirect to or embed, or server-to-server. Every check runs under the person's
consent, and when they withdraw it, FOID stops sending you their data.

- Base URL: `https://<foid-api>/api/open/v1` (local: `http://localhost:8000/api/open/v1`)
- Auth: `Authorization: Bearer FOID_TEST_…` (sandbox) or `FOID_LIVE_…` (live). The key is shown once at creation; FOID stores only a hash and a hint like `FOID_LIVE_28…29`
- Formats: JSON, snake_case, ISO-8601 UTC timestamps
- Interactive reference: `GET /docs` on the API host (OpenAPI)

---

## 1. Get keys

1. Sign in to FOID and create an organisation (business dashboard).
2. Create a **test** key — you can start immediately. Secrets are shown **once**.
3. For **live** keys, submit business verification (KYB: CAC RC number). FOID approves, then live keys
   can be created. Live keys are refused until then (`403 live_mode_disabled`).

```bash
curl https://<foid-api>/api/open/v1/ping -H "Authorization: Bearer FOID_TEST_..."
# {"ok": true, "organisation": "Acme", "env": "test"}
```

---

## 2. Hosted verification (recommended)

FOID shows the consent screen, runs the steps (NIN by number **or** by scanning an NIN slip / NIMC card,
BVN, liveness), and is branded with your name/logo plus "Secured by FOID". No camera code on your side.

### Create a verification (your server)

```bash
curl -X POST https://<foid-api>/api/open/v1/verifications \
  -H "Authorization: Bearer FOID_TEST_..." -H "Idempotency-Key: signup-8841" \
  -H "Content-Type: application/json" -d '{
    "checks": ["nin", "liveness"],
    "purpose": "Open a savings wallet",
    "customer_ref": "user_8841",
    "first_name": "Ada", "last_name": "Obi",
    "email": "ada@example.com",
    "return_url": "https://yourapp.com/kyc/done"
  }'
```

| Field | Notes |
|---|---|
| `checks` | Any of `nin`, `bvn`, `liveness`, `reverify` (`reverify` = liveness + 1:1 match against this person's earlier liveness face; can't be combined with `liveness`) |
| `purpose` | Shown to the person on the consent screen |
| `customer_ref` | Your id for the person. Reusing it reuses the same subject |
| `subject_id` | Alternative to `customer_ref` (required for `reverify`) |
| names / `date_of_birth` / `email` / `phone` | Names are matched against the NIN/BVN record. `email` helps link the person to a FOID account later |
| `scopes` | Extra scopes beyond what the checks imply: `contact`, `financial` |
| `return_url` | Redirect after finishing (`?verification_id=…&status=…&outcome=…`) |
| `metadata` | Up to your own string key/values, echoed back |

Response (`201`) includes `id`, `hosted_url` and `client_token`. While the verification is still `pending` /
`in_progress`, `GET /verifications/{id}` returns them again (e.g. to resend the link); once it is completed,
cancelled or expired they are `null`. They are never included in webhook payloads.

### Send the person to it

- **Redirect / link / QR**: open `hosted_url`.
- **Embed in your web app** (modal with the FOID-branded flow):

```html
<script src="https://<foid-app>/foid-verify.js"></script>
<script>
  FoidVerify.open({
    clientToken: 'vs_...',                       // from your server
    onComplete: (r) => confirmOnServer(r.verification_id),
    onCancel:   (r) => console.log('cancelled', r),
  })
</script>
```

- **Mobile apps**: open `hosted_url` in a WebView / in-app browser with camera permission.

Treat what the browser tells you as a hint only — confirm via webhook or `GET /verifications/{id}`.

### Read the result

`GET /verifications/{id}` →

```json
{
  "id": "…", "status": "completed", "outcome": "passed",
  "checks": ["nin", "liveness"],
  "consent": {"status": "active", "scopes": ["identity", "liveness"]},
  "results": {
    "nin": {"status": "passed", "reasons": [], "data": {"method": "document", "nin_last4": "8900",
            "document_type": "improved_nin_slip", "name_match": true, "dob_match": null,
            "record": {"first_name": "Ada", "middle_name": null, "last_name": "Obi", "date_of_birth": "1995-04-12"}}},
    "liveness": {"status": "passed", "data": {"face_quality": 0.82}}
  }
}
```

- `status`: `pending` → `in_progress` (consent given) → `completed` | `cancelled` | `expired` (link lifetime, default 24 h)
- `outcome` (when completed): `passed` (all checks passed) · `failed` · `needs_review`
- Each step allows **3 attempts**. Full NIN/BVN numbers are never returned or stored — last 4 only.
- `reused_foid_credential: true` means the person signed in to FOID and shared already-verified results.

Other endpoints: `GET /verifications?status=&customer_ref=&limit=&offset=`, `POST /verifications/{id}/cancel`.

---

## 3. Server-to-server checks

When you already collected the number **and the person's consent** yourself:

```bash
POST /checks/nin   {"number": "12345678900", "first_name": "Ada", "last_name": "Obi",
                    "date_of_birth": "1995-04-12", "customer_ref": "user_8841",
                    "consent": {"obtained": true, "purpose": "Loan application"}}
POST /checks/bvn   (same body)
POST /checks/nin-document   multipart: file (JPEG/PNG/WebP ≤ 8 MB), consent_obtained=true, purpose,
                            customer_ref?, first_name?, last_name?, date_of_birth?
```

`consent.obtained: true` is your legal attestation; FOID records it (`source: business_attested`).
The document check only **reads the NIN** from the slip/card (OCR) and then looks it up — the photo on
the document is not used.

Result:

```json
{"id": "…", "type": "nin", "status": "failed", "reasons": ["name_mismatch"],
 "data": {"method": "number", "nin_last4": "8908", "name_match": false, "name_score": 0.0, …},
 "subject_id": "…", "customer_ref": "user_8841"}
```

| `status` | Meaning |
|---|---|
| `passed` | Found, and first + last name match (date of birth too, if both sides have it) |
| `failed` | `not_found`, `name_mismatch`, `dob_mismatch`, `name_not_supplied`, `document_unreadable`, `unsupported_document`, `face_mismatch` |
| `needs_review` | e.g. `low_ocr_confidence` on a document scan |
| `error` | `provider_unavailable`, `ocr_unavailable` — not the person's fault; retry later. Not billed |

---

## 4. Subjects (the people you verify)

| Endpoint | |
|---|---|
| `GET /subjects?customer_ref=` | List |
| `GET /subjects/{id}` | Profile filtered by consent: `identity` → names, DOB, NIN/BVN verified + last 4; `contact` → email, masked phone; `liveness` → `passed_at` |
| `GET /subjects/{id}/checks` | All check results you're still allowed to see |
| `GET /subjects/{id}/trust-report` | FOID account holders only, scope `financial` (see below) |
| `DELETE /subjects/{id}` | Erase everything FOID holds about this person for you (checks, face, consent) |

`has_foid_account: true` tells you the person is (now) a FOID user.

### Trust report

Verified signals + the living credential state: `credential_state` (`active / under_review / downgraded /
revoked`), `income_band`, `account_stability`, `repayment_reliability`, `verification_completeness`
(0–100: how much of the identity is verified), dated `signals`. **Not a credit score and not a lending
recommendation** — the decision stays with you. Subscribe to `credential.state_changed` to hear when it changes.

---

## 5. Consent and revocation — what happens when a person says stop

- Consent is captured on FOID's page (or attested by you for server-to-server checks) and lists the
  scopes and purpose.
- The person can revoke at any time from **Connected apps** in their FOID account.
- On revocation, immediately:
  - `GET /subjects/{id}` and `/checks` return `403 {"error": {"code": "consent_revoked"}}`
  - `GET /verifications/{id}` still shows status/outcome but results become `{"status": …, "redacted": true}`
  - any queued webhooks about that person are **cancelled** and can't be re-sent
  - you receive exactly one `consent.revoked` event — stop using and delete what you hold, per your
    own obligations (NDPA 2023)

## 6. People who are not on FOID (yet)

You can verify anyone — they don't need a FOID account. FOID keeps a **subject** record for your
business only (each business has its own record of the same person; businesses never see each other's).

If the person later joins FOID, their subjects are linked to the new account **only with strong
evidence** — the NIN you verified must match theirs **and** either the verified email on their FOID
account matches the email you supplied, or their FOID liveness face matches the liveness face you
captured. (A NIN typed at signup alone is never enough.) Once linked:

- they see your business in **Connected apps**, marked "verified before you joined", and can revoke;
- you get a `subject.linked` event and `has_foid_account: true`;
- you get **no new data** — to read FOID-held data (e.g. the trust report) you must request it in a new
  verification and they must approve.

Sandbox (test-mode) subjects are never linked to real FOID accounts automatically.

---

## 7. Webhooks

Configure endpoints per environment in the dashboard (secret shown once; roll any time).

Events: `verification.completed`, `verification.cancelled`, `verification.expired`, `check.completed`
(server-to-server checks), `consent.revoked`, `subject.linked`, `credential.state_changed`, `webhook.test`.

```json
{"id": "evt_…", "type": "verification.completed", "env": "live", "created": 1793560000, "data": { …verification… }}
```

**Verify the signature** (reject if it fails or `t` is older than 5 minutes):

```
FOID-Signature: t=1793560000,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>
```

```python
import hmac, hashlib
def verify(secret: str, header: str, raw_body: bytes) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    mac = hmac.new(secret.encode(), f"{parts['t']}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, parts["v1"])
```

Respond `2xx` quickly. Failures retry with backoff (10 s → 6 h, 8 attempts); use `FOID-Event-Id` to dedupe.
Delivery logs, manual retry and a test-send are in the dashboard.

---

## 8. Sandbox

Test keys never touch real registries and are never billed. The **last digit** of an NIN/BVN decides:

| Last digit | Result |
|---|---|
| `0`–`7` | Found; the record echoes the name/DOB you sent → `passed` |
| `8` | Found under a different name → `failed` / `name_mismatch` |
| `9` | `failed` / `not_found` |

Liveness in sandbox is real (use your own face). The hosted page shows a **Sandbox** badge.

---

## 9. Errors, idempotency, limits

```json
{"error": {"type": "permission", "code": "consent_revoked", "message": "…", "param": null}}
```

Common codes: `missing_api_key`, `invalid_api_key`, `live_mode_disabled`, `invalid_nin`, `invalid_bvn`,
`subject_not_found`, `verification_not_found`, `no_face_on_file`, `consent_revoked`, `scope_not_granted`,
`idempotency_key_reused`, `too_many_attempts`, `verification_expired`.

- **Idempotency**: send `Idempotency-Key` on POSTs; a retry with the same key and body replays the first
  response (`Idempotent-Replayed: true`); a different body → `409 idempotency_key_reused`.
- **Rate limits**: 120 req/min per key (30/min for document uploads).
