# Enterprise console — backend integration plan (draft v2)

Status: **UI only, all data is placeholder** (`src/data/mock.ts`, read through `src/data/useData.ts`).
Nothing below is built yet. Review the UI, then we run the phases in order.

Run it: `cd enterprise && pnpm install && pnpm dev` → http://localhost:5174
(Vite proxies `/api/*` to `VITE_API_URL` or `http://localhost:8000`, same as `frontend/`.)

## Decisions (from review, 2026-11-02)
1. **Separate console login.** A console account is its own identity, even if the same person also
   has a FOID user account. Console sessions never touch user-app sessions or data.
2. **Real payments through Bachs**, sandbox for now. Reuse `backend/app/services/bachs_service.py`
   (checkout session + HMAC webhook verification, sandbox chosen by the `sk_sandbox_` key prefix).
3. **Users = everyone the business verified**, including people who are not on FOID (`subjects`).
4. **CBN licence number stays a placeholder** in Settings → Organization (not wired). Company name
   and support email are wired.
5. **Test mode is the default. Live is locked until FOID approves the business documents (KYB).**
   Test and Live are fully separate: users, keys, webhooks, request logs, usage, activity and charts
   all come from the selected environment. Org-level things (team, plan, invoices, settings) are shared.

6. **API keys are `FOID_LIVE_…` / `FOID_TEST_…`, shown once.** The full key is returned only by the
   create call. FOID stores a SHA-256 hash (for lookup) and a hint like `FOID_LIVE_28…29` — never the key.
   Old `sk_test_`/`sk_live_` keys keep working until revoked. ✅ done in Phase 1.

## Phase 1 — what was built
- Backend: `models/console.py` (console_users, console_refresh_tokens, console_otps),
  `routers/console_auth.py` (`/api/v1/console/auth/*`), console token type `"console"`,
  `get_console_user` / `require_verified_console_user`; `/business/*` now uses console accounts;
  migration `d0e1f2a3b4c5` (existing org members get console accounts with the same name, email
  and password hash, marked verified); new key format in `core/api_auth.py`.
- Console: `/login`, `/signup` (creates the org), `/verify-email`, `/forgot-password`;
  `ProtectedRoute` waits for the session to restore; org switcher + role from the backend;
  Test/Live remembered per org; Create-key buttons hidden below developer, danger zone owner-only.
- Tests: `tests/test_console.py` + updated business tests — 39 pass on SQLite and Postgres.

## What the UI already does (placeholder)
- `ModeContext`: `mode` (test | live), `kyb` (not_submitted | pending | approved | rejected).
  Live can't be selected while KYB isn't approved — the Live button shows a lock and opens `/go-live`.
- Orange "Test mode" strip under the topbar on every page, with a link to go live.
- `/go-live`: business details (RC number, TIN, address), 6 document uploads (licence optional),
  submit for review, 3-step progress. A small **"Preview approved (placeholder)"** link lets you see
  the Live pages now — **remove it when wiring**.
- Every page reads `useData()` → `DATA[mode]`, so switching swaps all numbers/tables.

---

## Phase 1 — Console accounts + org shell (backend + frontend) — ✅ DONE 2026-11-02
Backend (new):
- `console_users` table (id, name, email, password hash, email_verified_at, 2fa secret?, last_active_at,
  created_at). **Not** the `users` table. Same password rules as the user app.
- `/api/v1/console/auth/*`: signup (creates console user **and** organisation, sender is owner),
  login, refresh (rotating), logout, verify-email, forgot/reset password. Separate JWT audience
  (`aud="console"`) + separate refresh-token table, so a user-app token is rejected by the console
  and vice versa.
- Move `org_members.user_id` → `console_user_id` (migration). `business.py` switches its dependency
  from `get_current_user` to `get_console_user`; role checks stay as they are.
- Rate limits like the user auth routes (`10/minute`).

Frontend:
- Login, signup (name, email, password, company name), verify-email, forgot-password pages —
  copy `frontend/src/pages/auth/*` + `AuthContext` + `ProtectedRoute`; refresh token key
  `foid_console_refresh_token` (separate from the user app).
- `OrgContext`: orgs list, current org (remembered), role, plus `kyb`/`live_enabled` from the org →
  replaces the placeholder state in `ModeContext`. Mode remembered per org in localStorage.
- Sidebar switcher becomes a real dropdown; Topbar shows the signed-in member + role.
- Hide/disable actions by role (viewer can't create keys; only owner/admin see billing + danger zone).

## Phase 2 — Go live (KYB documents) — ✅ DONE 2026-11-02
Built: `routers/kyb.py` (business side), admin review + download in `routers/admin.py`, `services/kyb_service.py` (document list, PDF/JPEG/PNG checked by content, 10 MB), `kyb_documents` table (Fernet-encrypted in the database), org fields tin / registered_address / kyb_submitted_at / kyb_reviewed_at / kyb_note, migration `e1f2a3b4c5d6`, owner emails on received / approved / rejected, `tests/test_kyb.py`. Console `/go-live` is wired (preview placeholder removed). Still missing: an admin review screen (API only).

Exists: `POST /business/organisations/{id}/kyb` (sets `rc_number`, status `pending`),
admin `POST /admin/organisations/{id}/kyb` approve/reject → sets `live_enabled`,
and `core/api_auth.py` already rejects live keys when `live_enabled` is false.
Add:
- `kyb_documents` table (org_id, type, file path, sha256, size, mime, uploaded_by, created_at).
  Files stored outside the web root, encrypted at rest (same Fernet approach as faces), served to
  FOID admins only. Accept PDF/JPEG/PNG ≤ 10 MB; check the file signature, not just the extension.
- `POST /organisations/{id}/kyb/documents` (multipart, owner/admin), `GET` list, `DELETE` before submit.
- Extend `KybSubmit` with `tin`, `registered_address`; reject submit until required docs exist.
- `rejected` → reason shown on `/go-live`, documents can be replaced and resubmitted.
- Email the owner on approve/reject; audit log entries for every step.
- Admin side: list pending orgs + download documents (admin router already lists by `kyb_status`).

## Phase 3 — Wire existing endpoints (mostly frontend), all with `env` — ✅ DONE 2026-11-02
Built: `GET /organisations/{id}/users` (status verified/pending/declined/revoked, search by name/email/FOID code/ref — only fields consent allows, counts for the cards), richer `/overview` (users, 30-day verifications + trend, pass rate, avg time, funnel, stuck), keys `?env=` + hide revoked + `POST /api-keys/{id}/rotate`, webhooks `?env=` + last delivery status (`delivered` / `failed` / `retrying`), `services/console_views.py`, `tests/test_console_views.py`. Console: API keys & webhooks (create / regenerate / revoke, add / test / rotate secret / delete; secrets shown once), Users (real table, 25 per page, search, tabs, detail panel), Overview cards + funnel, Team (add existing console account, change role, remove), Settings → company name + support email, live Users badge. Still sample: API-requests chart, recent activity, request logs, billing (Phases 4–5).

| UI | Endpoint (exists) | Small additions |
|---|---|---|
| API keys | `GET/POST/DELETE /organisations/{id}/api-keys` | filter by `env`; `POST /api-keys/{kid}/rotate`; create-key modal shows the raw key **once** |
| Webhooks | `GET/POST/PATCH/DELETE /webhooks`, `/test`, `/roll-secret`, `/deliveries` | filter list by `env` (column exists); `last_delivery_status`, `last_delivered_at` |
| Users table | `GET /organisations/{id}/subjects?env` | `total`, `status` filter, `q` over name / email / FOID code (today exact `customer_ref` only), `GET /subjects/summary?env` for the 4 cards |
| User detail | `GET /subjects/{sid}` (consent-filtered) | detail drawer UI |
| Overview cards + funnel | `GET /organisations/{id}/overview?env` | avg verification time, trend vs last period, funnel buckets + "stuck" count |
| Team | `GET/PATCH/DELETE /members` | invites (Phase 6) |
| Settings → Organization | `PATCH /organisations/{id}` | company name + support email only; CBN licence stays placeholder |

## Phase 4 — Request logs, activity feed, charts — ✅ DONE 2026-11-02
Built: `api_request_logs` (migration `f2a3b4c5d6e7`) written by middleware on `/api/open/*` with a `FOID-Request-Id` header on every response (method, path without query string, status, latency, key hint — no bodies or personal data; unknown keys aren't stored; 30-day retention in the cleanup loop, which now also purges used console tokens/codes), `routers/console_data.py`: request-logs, request-stats, activity, search, users/request-logs CSV export (formula-safe; users export reviewer+), `tests/test_console_data.py`. Console: Request logs page, Overview API-requests card + chart + recent activity, top-bar search (people and req_ IDs), Export buttons. Only billing is still sample data (Phase 5).

- `api_request_logs` (org_id, env, key_id, request_id, method, path, status, latency_ms, created_at),
  written by middleware on `/api/open/v1/*` only. No bodies, no PII. 30-day retention, swept in the
  existing minute loop in batches.
- `GET /organisations/{id}/request-logs?env&status_class&q&limit&offset`
- `GET /organisations/{id}/request-stats?env&days=30` → daily successful/failed for the chart.
- `GET /organisations/{id}/activity?env` → verifications + webhook deliveries + team actions, viewer+.
- Topbar search: `GET /organisations/{id}/search?env&q=` (users, FOID codes, request IDs).
- CSV exports (users, logs, invoices).

## Phase 5 — Billing with Bachs (sandbox) — ✅ DONE 2026-11-02
Built: placeholder plans in `services/billing_service.PLANS` (Starter free / Growth ₦150k / Business ₦420k / Enterprise custom — edit there), `organisations.plan_code` + period, `invoices` table (migration `a3b4c5d6e7f8`), `routers/billing.py` (plans, billing view with live/test usage + limit projection, checkout, pay invoice, invoice status, PDF). Payments: Bachs checkout with reference `inv_…`; the existing `/wallet/bachs-webhook` (one URL in the Bachs dashboard) hands `inv_` references to `billing_service.confirm_payment` after the signature check — amount must match, retries are harmless. Renewal invoices open from the cleanup loop. New setting `CONSOLE_URL` (Bachs return page). `tests/test_billing.py`; tests now blank `BACHS_*` so they can never reach Bachs. Not yet: unpaid-renewal enforcement, 80%/100% usage emails, limit throttling, receipts by email.

- `plans` (code, name, monthly price ₦ in kobo, included verifications, seats, features) seeded with the
  Business plan; `organisations.plan_code`, `current_period_end`.
- `invoices` (org_id, number `INV-YYYY-NNNN`, period, amount, status draft|due|paid|void, bachs_reference,
  paid_at, pdf). Only **live** usage is billed; test usage is shown but free.
- Upgrade / pay invoice → `bachs_service.create_checkout_session(reference=invoice id, metadata={org_id, plan})`
  → redirect to `checkout_url` → back to `/billing?paid=…`.
- Webhook: new `POST /api/v1/business/bachs-webhook` (or route by metadata in the existing
  `/wallet/bachs-webhook`) — verify signature, idempotent on reference, mark invoice paid, change plan.
  Never trust the redirect alone.
- Limit + projection from live `usage_events`; email at 80% / 100%.
- Invoice PDF download (same approach as the identity-summary PDF).
- Env: `BACHS_API_KEY=sk_sandbox_…`, `BACHS_WEBHOOK_SECRET` (already in `Settings`).

## Phase 6 — Team invites, security, danger zone — ✅ DONE 2026-11-02
Built (migration `b4c5d6e7f8a9`): `org_invites` (7-day emailed link, only a hash stored; accept creates the console account — email counts as verified — or joins an existing one when signed in as that email; resend issues a new link and kills the old one; plan seat limits enforced), two-step sign-in for console accounts (`core/totp.py`, RFC 6238, codes work once; login → `mfa_required` → `/login/2fa`), Security settings (`require_2fa` blocks members without it from that business; `alert_on_key_create` emails owners/admins; IP allow-list for live keys, IPs or CIDR ranges), danger zone (owner: revoke all keys; deactivate with typed name → API, webhooks and console stop, reactivate within 30 days, then the cleanup loop deletes the business), up to 5 businesses per account until one is approved for Live. Console: My account page (profile, password, two-step sign-in with QR, your businesses), Create another business in the switcher, invite acceptance page `/invite/:token`, Team invites, Security + Danger zone wired. `tests/test_org_admin.py`.

- `org_invites` (email, role, token hash, expires 7 days, invited_by); accept page creates the console
  account if needed; resend; pending row as in the design.
- `org_settings`: `require_2fa`, `alert_on_key_create`, `ip_allowlist`; allowlist enforced in
  `core/api_auth.py` for live keys; email alert on key creation.
- 2FA (TOTP) for console accounts — can ship the toggle as "coming soon" first.
- Owner-only: revoke all keys, deactivate org (`status=suspended`, 30-day retention), typed confirmation.

---

## Still open
- Which documents are required vs optional (current list: CAC certificate, CAC status report, MEMART,
  director's ID, proof of address; licence optional) — confirm with compliance.
- Plan prices/limits beyond the one "Business plan" in the design.
- Who reviews KYB on the FOID side (admin UI is not designed yet — today it's API only).
