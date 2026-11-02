# FOID for Business — dashboard design brief

For the designer of the **business dashboard** (fintechs using the FOID Open API). The backend is
built; every screen below maps to real endpoints, fields and states so the design can be wired
without guesswork. Developer API reference: [`open-api.md`](open-api.md).

All dashboard endpoints are `GET/POST/PATCH/DELETE /api/v1/business/organisations/{org_id}/…`, signed in
as a normal FOID user who belongs to the organisation.

---

## 1. Design system (reuse the FOID consumer app's)

| Token | Value | Use |
|---|---|---|
| Brand primary | `#C800DE` (wordmark/accents), Tailwind `brand-500` `#c026d3` (buttons) | Primary buttons, active nav, focus rings |
| Brand scale | `brand-50 #fdf4ff` · `100 #fae8ff` · `200 #f5d0fe` · `300 #e879f9` · `400 #d946ef` · `600 #a21caf` · `700 #86198f` · `900 #4a044e` | Tints for badges, selected rows, hover |
| Neutrals | `50 #fafafa` · `100 #F2F2F2` · `200 #e4e4e7` · `400 #a1a1aa` · `500 #71717a` · `700 #3f3f46` · `900 #18181b` | Surfaces, borders, text |
| Status — success | brand tint `#f5d0fe` bg / `#a21caf` text | Passed, Active, Delivered |
| Status — danger | `#fee2e2` / `#dc2626` | Failed, Revoked, Failed delivery |
| Status — warning | `#fef9c3` / `#a16207` | Needs review, Pending KYB, Retrying |
| Status — neutral | outline `#d4d4d8` / `#71717a` | Pending, Cancelled, Expired |
| **Sandbox** | amber `#fef3c7` / `#b45309` | Everything in test mode (see §2) |
| Fonts | CreatoDisplay (UI), NeueMachina (display headings) | Already bundled |
| Icons | Remix Icon (`ri-*-line` / `-fill`) | Already bundled |
| Radius | cards `rounded-2xl` (16px), inputs/buttons `rounded-lg`–`rounded-full` | Match consumer dashboard |
| Logo | `FoidWordmark` component, "FOID for Business" lockup | Sidebar + auth |

Components already in the consumer app to reuse: `StatCard`, `SegmentedTabs`, `Card`, data table
style from `ConsentPage`, `Sidebar`/`Topbar` layout, `RemixIcon`.

**New components the business dashboard needs:** environment switch, secret reveal box, code
snippet block (copy button), JSON viewer (collapsible), status pill set (below), timeline, check
result card, empty states, role badge, confirmation dialog (typed confirm for destructive actions),
date-range filter, pagination.

---

## 2. Global patterns

- **Organisation switcher** (top-left): a user may belong to several orgs —
  `GET /api/v1/business/organisations` → `[{id, name, logo_url, role, kyb_status, live_enabled}]`.
- **Environment switch: Test ↔ Live** (always visible, top bar). Every list/overview takes `env=test|live`.
  Test mode must look obviously different (amber "Sandbox" ribbon/badge) so nobody mistakes fake data
  for real customers. Live is disabled with a tooltip until KYB is approved (`live_enabled: false`).
- **Roles** gate what's shown: `owner > admin > developer > reviewer > viewer`. Hide (don't just disable)
  sections a role can't use: API keys & webhooks need `developer+`, team & settings need `admin+`,
  KYB submit needs `owner`, audit log `admin+`.
- **Secrets are shown once** (API keys, webhook signing secrets): modal with copy button + "I've stored
  it" confirmation; afterwards only the prefix is visible (`sk_test_AbC12…`).
- **Consent is visible everywhere a person appears**: a consent pill (`Active` / `Revoked` / `None`). When
  revoked, personal data is not returned by the API — design a **redacted state** ("This person withdrew
  consent on 3 Nov — details hidden") instead of empty fields.
- Errors come back as `{error: {type, code, message, param}}` — show `message`; use `param` to point at a field.

### Status pills (one consistent set)

| Object | Values |
|---|---|
| Verification `status` | `pending` (link sent, not opened/consented) · `in_progress` · `completed` · `cancelled` · `expired` |
| Verification `outcome` | `passed` · `failed` · `needs_review` (only when completed) |
| Check `status` | `pending` · `passed` · `failed` · `needs_review` · `error` (provider/OCR down — not the person's fault) · plus `redacted` |
| Consent | `active` · `revoked` · `none` |
| Webhook delivery | `pending` (show "retrying at …") · `delivered` · `failed` · `cancelled` ("consent revoked" / "endpoint disabled") |
| KYB | `not_submitted` · `pending` · `approved` · `rejected` |

---

## 3. Screens

### 3.1 Onboarding
1. **Create organisation** — name, website, support email → `POST /organisations`.
2. **Get started checklist** (on Overview until done): create test key → create webhook → run a test
   verification → submit KYB → go live.

### 3.2 Overview — `GET …/overview?env=`
```json
{"verifications": {"total": 120, "by_status": {"completed": 96, "in_progress": 8, "expired": 16},
  "by_outcome": {"passed": 81, "failed": 12, "needs_review": 3}, "pass_rate": 0.844},
 "checks_run": {"nin": 110, "liveness": 97, "bvn": 40}, "reused_foid_credential": 23}
```
Stat cards (verifications, pass rate, checks run, **reused FOID identity** — highlight this, it's the
product's selling point: "23 customers verified in one tap"), a chart of verifications over time (use the
list endpoint by date), recent verifications table.

### 3.3 Verifications list — `GET …/verifications?env=&status=&outcome=&limit=&offset=`
Columns: person (`subject_name`, or "Hidden — consent revoked"), `customer_ref`, checks (icons),
status, outcome, consent pill, "via FOID identity" badge (`reused_foid_credential`), created.
Filters: status, outcome, date. Row → detail.

### 3.4 Verification detail — `GET …/verifications/{id}`
- Header: person, `customer_ref`, status + outcome, created/completed/expires.
- While open (`hosted_url` not null): **Copy link** / **Show QR** / **Resend** actions for the hosted page.
- **Check cards** (one per `results[check]`):
  - NIN / BVN: method (number / document scan + `document_type`), last 4, name match ✓/✗ + `name_score`,
    DOB match, record name/DOB, `reasons` in plain language, attempts.
  - Liveness: passed/failed, face quality, (reverify) match score + matched.
  - Redacted variant when consent is revoked.
- **Consent panel**: scopes + descriptions, source (`hosted_flow` / `business_attested`), granted/revoked at.
- **Timeline**: `timeline[]` (created → consent granted → FOID identity shared → completed).
- Metadata (key/values you sent).

Human-readable reason copy:
`not_found` "No record for that number" · `name_mismatch` "Name doesn't match the record" ·
`dob_mismatch` "Date of birth doesn't match" · `document_unreadable` "NIN couldn't be read from the image" ·
`unsupported_document` "Not an NIN slip / NIMC card" · `low_ocr_confidence` "Image hard to read — review" ·
`face_mismatch` "Face didn't match the one on file" · `provider_unavailable` / `ocr_unavailable`
"Service temporarily unavailable".

### 3.5 Customers (subjects) — `GET …/subjects?env=&q=`, `GET …/subjects/{id}`
List + profile: names, DOB, NIN/BVN verified + last 4, liveness passed at, `has_foid_account`
("Has a FOID account" badge — they can manage consent themselves), consent pill, all checks.

### 3.6 Developers
- **API keys** — `GET/POST …/api-keys`, `DELETE …/api-keys/{id}`. Table: name, env, prefix, last used,
  created, revoked. Create → secret-once modal. Live key button locked until KYB approved.
- **Webhooks** — `GET/POST/PATCH/DELETE …/webhooks`, `POST …/webhooks/{id}/test`,
  `POST …/webhooks/{id}/roll-secret`, event list from `GET /api/v1/business/webhook-event-types`.
  Endpoint detail: **delivery log** `GET …/webhooks/{id}/deliveries?status=` (event type, status pill,
  attempts, last HTTP code/error, next retry, payload JSON viewer, **Retry** button — disabled with
  explanation for consent-revoked deliveries).
- **Quick start**: code snippets (curl / Node / Python) for create verification + embed script, sandbox
  test numbers table (last digit 0–7 pass, 8 name mismatch, 9 not found), link to API docs.
- **Hosted page preview**: show how their logo/brand colour appears on the FOID-hosted page.

### 3.7 Settings
- **Branding** — `PATCH …/{org_id}` `{name, logo_url, brand_color (#RRGGBB), website, support_email}`
  with a live preview of the hosted verification page header.
- **Business verification (KYB)** — `POST …/kyb {rc_number}`; states per `kyb_status`.
- **Team** — `GET/POST/PATCH/DELETE …/members` (invite by email of an existing FOID account, role select;
  owner can't be changed/removed).
- **Audit log** — `GET …/audit-log` (action, actor, target, time, meta).

### 3.8 Usage / billing — `GET …/usage?env=live&month=YYYY-MM`
`{by_check: {nin: 40, liveness: 31}, billable: 71}` — per-check counts for the month. (Pricing and
wallet top-up are a later phase; leave room for a price column and balance.)

---

## 4. The hosted verification page (already built — for reference/consistency)

What the business's customers see at `/verify/{token}` (or embedded via `foid-verify.js`). It's
FOID-branded with the business's name/logo/colour on top and "Secured by FOID" at the bottom,
mobile-first, 440px card:

consent screen (business wants to verify you · purpose · what they'll see · I agree / Decline) →
optional "Use my verified FOID identity" (signed-in FOID users) → steps (NIN: enter number **or** scan
NIN slip/card · BVN · liveness camera with live prompts) with attempts left → done (redirects back).

A visual polish pass by the designer is welcome — keep the structure and states:
`loading`, `invalid/expired link`, `consent`, `step (idle / submitting / failed with reason / attempts
exhausted)`, `liveness (camera starting / prompt / processing / failed / passed)`, `completed`,
`cancelled`, `expired`, plus the **Sandbox** badge.

---

## 5. Consumer side (FOID app) touch-point

The FOID user's **Consent Requests** page (`/dashboard/consents`) now lists real businesses from
`GET /api/v1/connected-apps` with **Revoke access** (`DELETE /api/v1/connected-apps/{org_id}`), including
businesses that verified the person *before* they joined FOID ("verified before you joined"). If the
designer revisits that page: add a detail drawer showing each business's checks and consent history
(`grants[]`, `checks[]`).
