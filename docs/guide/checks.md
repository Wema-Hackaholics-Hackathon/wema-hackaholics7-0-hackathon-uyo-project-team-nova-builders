# NIN and BVN checks

Server-to-server lookups for when you already hold the number **and the person's consent**, for example from your own onboarding form. FOID looks the number up and tells you whether the name and date of birth you hold match the record. There's no face check and no FOID page: use [hosted verification](./hosted-verification) when you need those.

## Run a check

::: code-group

```bash [curl]
curl https://api.foid.ng/api/open/v1/checks/nin \
  -H "Authorization: Bearer $FOID_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "number": "12345678901",
    "first_name": "Ada", "last_name": "Obi", "date_of_birth": "1994-03-12",
    "customer_ref": "cust_1001",
    "consent": { "obtained": true, "purpose": "Account opening" }
  }'
```

```python [Python]
result = foid.check_nin(
    number="12345678901",
    first_name="Ada", last_name="Obi", date_of_birth="1994-03-12",
    customer_ref="cust_1001",
    consent={"obtained": True, "purpose": "Account opening"},
)
```

```js [Node]
const result = await foid.checkNin({
  number: '12345678901',
  first_name: 'Ada', last_name: 'Obi', date_of_birth: '1994-03-12',
  customer_ref: 'cust_1001',
  consent: { obtained: true, purpose: 'Account opening' },
})
```

:::

`POST /checks/bvn` (`check_bvn` / `checkBvn`) takes the same body.

| Field | Notes |
|---|---|
| `number` | The 11-digit NIN or BVN. Anything else is refused with `400 invalid_nin` / `invalid_bvn`. FOID never stores it: only a keyed hash and the last 4 digits. |
| `consent.obtained` | Must be `true`: your statement that the person agreed to this check. |
| `consent.purpose` | Why you're checking, 3–200 characters. Recorded with the consent. |
| `first_name`, `middle_name`, `last_name` | The name you hold. First and last name are matched against the record. |
| `date_of_birth` | `YYYY-MM-DD`. Matched when both sides have it. |
| `customer_ref` / `subject_id` | Which [subject](./concepts#subjects) this belongs to. Reusing `customer_ref` reuses the subject. |
| `email`, `phone` | Optional, stored on the subject. |

Both endpoints accept an `Idempotency-Key` header, so a retry isn't billed twice. See [Idempotency](./errors#idempotency).

### Consent attestation

`consent.obtained: true` is your legal attestation that you collected the person's consent yourself. FOID records it as a consent grant with source `business_attested` (the weakest kind), and the person sees it labelled that way in their FOID app if they have one. Without `consent`, or with `obtained: false`, the request is refused with `422`.

## The result

```json
{
  "id": "880af60a-e95c-4679-b205-21e710d775e9",
  "type": "nin",
  "status": "passed",
  "reasons": [],
  "data": {
    "method": "number",
    "nin_last4": "8901",
    "name_match": true,
    "name_score": 1.0,
    "dob_match": true,
    "record": { "first_name": "Ada", "middle_name": null, "last_name": "Obi", "date_of_birth": "1994-03-12" }
  },
  "provider": "mock",
  "verification_id": null,
  "subject_id": "c9981038-6db3-4236-8fca-d8bbb89dadfa",
  "created_at": "2026-11-03T20:25:02.091651+00:00",
  "customer_ref": "cust_1001"
}
```

| Field | Meaning |
|---|---|
| `status` | `passed`, `failed`, `needs_review` or `error`. See below. |
| `reasons` | Why it didn't pass. Empty when `passed`. |
| `data.nin_last4` / `data.bvn_last4` | The last 4 digits. Never the full number. |
| `data.name_match`, `data.name_score` | Whether the name matched, and how closely (0–1). |
| `data.dob_match` | `true` / `false`, or `null` if either side had no date of birth. |
| `data.record` | The name and date of birth on the record. |
| `subject_id` | The subject this check is now attached to. |
| `provider` | Which identity provider answered (`mock` in test mode). |

### Statuses and reasons {#statuses-and-reasons}

| `status` | `reasons` | Meaning |
|---|---|---|
| `passed` | — | Found, and first + last name match (and date of birth, if both sides have one). |
| `failed` | `not_found` | No record for this number. |
| | `name_mismatch` | Found, but the name you sent doesn't match. |
| | `dob_mismatch` | Found, but the date of birth doesn't match. |
| | `name_not_supplied` | You didn't send a name to match. |
| | `document_unreadable`, `unsupported_document` | Document check: couldn't read an NIN from the image. |
| `needs_review` | `low_ocr_confidence` | Document check: an NIN was read, but not confidently. |
| `error` | `provider_unavailable`, `ocr_unavailable` | Not the person's fault. Retry later. **Not billed.** |

In test mode, the last digit of the number picks the result. See [sandbox numbers](./test-and-live#sandbox-numbers).

Each check also sends a `check.completed` [webhook](./webhooks) with the same result.

## Check an NIN from a document

`POST /checks/nin-document` reads the NIN from a photo of an NIN slip or NIMC card (OCR), then looks it up like `/checks/nin`. The face on the document isn't used. It's a `multipart/form-data` upload:

```bash
curl https://api.foid.ng/api/open/v1/checks/nin-document \
  -H "Authorization: Bearer $FOID_API_KEY" \
  -F file=@nin-slip.jpg \
  -F consent_obtained=true \
  -F purpose="Account opening" \
  -F customer_ref=cust_1001 \
  -F first_name=Ada -F last_name=Obi
```

- If you don't send a name, the name printed on the document is used for the match.
- `file`: JPEG, PNG or WebP, up to 8 MB (`400 unsupported_file_type`, `413 file_too_large`).
- `consent_obtained` must be `true` (`400 consent_required`).
- Limited to 30 requests per minute.
- The SDKs don't have a helper for this endpoint yet. Call it with your HTTP client.

## Reading checks later

Every check is stored on the subject: [`GET /subjects/{id}/checks`](/api/reference#get-subjects-subject-id-checks) lists the ones your consent still covers. See [Subjects and consent](./subjects).
