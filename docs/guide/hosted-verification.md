# Hosted verification

Send a customer to a FOID-hosted page that collects their consent and runs the checks you ask for: NIN (by number, or by scanning an NIN slip or NIMC card), BVN and a liveness check. The page is branded with your business name and logo, plus "Secured by FOID". You write no camera code and no consent screen.

The person does **not** need a FOID account. If they have one, the page offers "Already have FOID? Sign in to share it instead", and they can share their existing verified results.

## 1. Create a verification (your server)

::: code-group

```bash [curl]
curl https://foid-iy7u.onrender.com/api/open/v1/verifications \
  -H "Authorization: Bearer $FOID_API_KEY" \
  -H "Idempotency-Key: onboard-cust_1001" \
  -H "Content-Type: application/json" \
  -d '{
    "checks": ["nin", "liveness"],
    "purpose": "Open a wallet",
    "customer_ref": "cust_1001",
    "first_name": "Ada", "last_name": "Obi",
    "return_url": "https://acme.example/kyc/done"
  }'
```

```python [Python]
v = foid.create_verification(
    checks=["nin", "liveness"],
    purpose="Open a wallet",
    customer_ref="cust_1001",
    first_name="Ada", last_name="Obi",
    return_url="https://acme.example/kyc/done",
    idempotency_key="onboard-cust_1001",
)
```

```js [Node]
const v = await foid.createVerification({
  checks: ['nin', 'liveness'],
  purpose: 'Open a wallet',
  customer_ref: 'cust_1001',
  first_name: 'Ada', last_name: 'Obi',
  return_url: 'https://acme.example/kyc/done',
  idempotencyKey: 'onboard-cust_1001',
})
```

:::

| Field | Notes |
|---|---|
| `checks` | One or more of `nin`, `bvn`, `liveness`, `reverify`. `reverify` is a liveness check matched 1:1 against this subject's earlier liveness face. Use it instead of `liveness`, not with it, and only for a subject that already has a face on file (`409 no_face_on_file` otherwise). |
| `purpose` | Shown to the person on the consent screen. 3–200 characters. |
| `customer_ref` | Your ID for the person. Reusing it reuses the same [subject](./concepts#subjects). |
| `subject_id` | Alternative to `customer_ref`; needed for `reverify`. |
| `first_name`, `middle_name`, `last_name`, `date_of_birth` | Matched against the NIN / BVN record. `date_of_birth` is `YYYY-MM-DD`. |
| `email`, `phone` | Optional. `email` helps link the person to a FOID account later. |
| `scopes` | Extra scopes beyond what the checks imply: `contact`, `financial`. |
| `return_url` | Where the page sends the person when they finish or cancel. |
| `metadata` | Your own string key/value pairs, echoed back. |

Send an `Idempotency-Key` so a retried request doesn't create a second verification. See [Idempotency](./errors#idempotency).

The response (`201`) is the verification, including `id`, `status: "pending"`, `hosted_url` and `client_token`. Field by field: [`POST /verifications`](/api/reference#post-verifications).

## 2. Send the person to it

**Redirect, link or QR code.** Open `hosted_url`, e.g. `https://usefoid.pages.dev/verify/vs_…`.

**Embed it in your web page.** `foid-verify.js` opens the same flow in a modal over your page:

```html
<script src="https://usefoid.pages.dev/foid-verify.js"></script>
<script>
  // client_token comes from YOUR server (the create call above)
  FoidVerify.open({
    clientToken: 'vs_…',
    onComplete: (r) => confirmOnServer(r.verification_id),   // { verification_id, status, outcome }
    onCancel:   (r) => console.log('cancelled', r),
    onClose:    ()  => console.log('modal closed'),
  })
</script>
```

| `FoidVerify` | |
|---|---|
| `open({ clientToken, onComplete, onCancel, onClose, origin, url })` | Opens the modal. Pass `clientToken`, or a full `url` (the `hosted_url`). `origin` overrides where the page is loaded from (defaults to the origin the script came from). Only one modal is open at a time. |
| `close()` | Closes it. Escape and the × button also close it. |
| `version` | Script version string. |

The iframe is allowed camera access. Results are only accepted from the FOID origin, and the modal closes itself shortly after `onComplete` / `onCancel`.

**Mobile apps** (React Native, Flutter, native): open `hosted_url` in a WebView or in-app browser **with camera permission**, and watch for navigation to your `return_url`.

::: warning
What the browser tells you is a hint only. Always confirm on your server with the `verification.completed` webhook or `GET /verifications/{id}`.
:::

## 3. What the person sees

1. Your branding, the purpose and the scopes, then a consent screen. Declining cancels the verification.
2. Each step in turn: NIN (number or document scan), BVN, liveness. Each step allows **3 attempts**.
3. A finish screen. With `return_url`, they're redirected after a moment to:

```
https://acme.example/kyc/done?verification_id=…&status=completed&outcome=passed
```

## 4. Read the result

::: code-group

```python [Python]
v = foid.get_verification(verification_id)
```

```js [Node]
const v = await foid.getVerification(verificationId)
```

:::

```json
{
  "id": "…",
  "object": "verification",
  "status": "completed",
  "outcome": "passed",
  "checks": ["nin", "liveness"],
  "consent": { "status": "active", "scopes": ["identity", "liveness"] },
  "reused_foid_credential": false,
  "results": {
    "nin": { "status": "passed", "reasons": [], "data": { "method": "number", "nin_last4": "8901", "name_match": true, "dob_match": null } },
    "liveness": { "status": "passed", "data": { "face_quality": 0.82 } }
  }
}
```

(Shortened; see the [full response](/api/reference#get-verifications-verification-id).)

**`status`:** `pending` (created) → `in_progress` (consent given) → `completed`, `cancelled` or `expired`.

**`outcome`** (once completed):

| `outcome` | Meaning |
|---|---|
| `passed` | Every requested check passed. |
| `failed` | At least one check failed or errored, or wasn't finished. |
| `needs_review` | Nothing failed, but something needs a human look (e.g. `low_ocr_confidence` on a document scan). |

Each entry in `results` is a check result (see [check statuses and reasons](./checks#statuses-and-reasons)), or `{"status": "pending"}` for a step not done yet. If the person later revokes consent, results come back as `{"status": "passed", "redacted": true}`: you keep the outcome, not the data.

`reused_foid_credential: true` means the person signed in with FOID and shared results they had already verified.

`hosted_url` and `client_token` are returned while the verification is still `pending` or `in_progress`, so you can resend the link. They become `null` once it's closed, and they are never included in webhooks.

## Webhooks

Subscribe to these in [Webhooks](./webhooks):

- `verification.completed`: the full verification (same shape as above, without the link).
- `verification.cancelled`: the person declined, or you cancelled.
- `verification.expired`: nobody finished it in time.

## Cancel and expiry

- **Cancel** an open verification with `POST /verifications/{id}/cancel` (`request()` in the SDKs). Cancelling a closed one returns `409 verification_closed`.
- **Expiry:** links live for **24 hours** by default (the FOID server's `VERIFICATION_TTL_HOURS`). After that the status becomes `expired` and the page refuses the link.
- **List** with `GET /verifications?status=&customer_ref=&limit=&offset=`.

## Re-verify a returning customer

To confirm it's still the same person (before a large withdrawal, a device change or a password reset), create a verification with `checks: ["reverify"]` and the `subject_id`. The person does a liveness check and FOID matches it against the face captured in their earlier verification.

```json
{ "checks": ["reverify"], "subject_id": "c9981038-…", "purpose": "Confirm it's you before a large transfer" }
```
