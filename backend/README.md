# FOID Backend

FastAPI backend for the FOID Identity & Digital Risk Assessment platform.

## Stack

| Package | Purpose |
|---|---|
| **FastAPI + Uvicorn** | Async HTTP server |
| **SQLModel** (SQLAlchemy 2 + Pydantic v2) | ORM — models are both DB tables and Pydantic schemas |
| **aiosqlite / asyncpg** | SQLite (dev) and PostgreSQL (prod) async drivers |
| **Alembic** | Database migrations |
| **Argon2-cffi** | Password hashing (Argon2id) |
| **python-jose** | HS256 JWT access tokens |
| **Groq** | AI receipt OCR and financial chat |
| **faceliveness 0.1** | Server-side active liveness (head turns / mouth), signed Ed25519 receipts |
| **OpenCV 4.10 + SFace** | JPEG frame decode; SFace (Apache-2.0) face embeddings for 1:1 matching |
| **httpx** | Async HTTP client for Mono, Bachs, webhooks |
| **fpdf2** | PDF report and identity summary generation |
| **slowapi** | Per-IP rate limiting |
| **Redis** | Optional response cache — gracefully disabled if `REDIS_URL` is unset |

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.4

---

## Setup

```bash
# 1. Enter the backend directory — MUST run from here, not repo root
cd backend

# 2. Install all dependencies
uv sync

# 3. Copy and fill in environment variables
cp .env.example .env
# Required: SECRET_KEY, GROQ_API_KEY
# Optional: MONO_SECRET_KEY, MONO_PUBLIC_KEY, BACHS_API_KEY, BACHS_WEBHOOK_SECRET, REDIS_URL
```

---

## Running

```bash
# Dev server with hot-reload
cd backend
uv run uvicorn app.main:app --reload --port 8000

# Or use the project script alias
uv run foid-dev
```

| URL | Purpose |
|---|---|
| `http://localhost:8000/docs` | Interactive Swagger UI |
| `http://localhost:8000/redoc` | ReDoc API docs |
| `http://localhost:8000/health` | Health check (`{"status": "healthy"}`) |
| `http://localhost:8000/openapi.json` | Raw OpenAPI spec |

---

## Docker

```bash
# Build
cd backend
docker build -t foid-backend .

# Run (SQLite, ephemeral)
docker run -p 8000:8000 --env-file .env foid-backend

# Run with PostgreSQL and persistent uploads
docker run -p 8000:8000 \
  --env-file .env \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/foid" \
  -v $(pwd)/uploads:/app/uploads \
  foid-backend
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | JWT signing key — use a long random string in production |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./foid.db` | SQLite for dev, `postgresql+asyncpg://...` for prod |
| `GROQ_API_KEY` | **Yes** | — | Groq API key — receipt OCR and AI chat |
| `MONO_PUBLIC_KEY` | No | — | Mono Connect public key (bank linking) |
| `MONO_SECRET_KEY` | No | — | Mono server-side secret key |
| `BACHS_API_KEY` | No | — | Bachs payment API key (`sk_sandbox_...` or `sk_live_...`) |
| `BACHS_WEBHOOK_SECRET` | No | — | Bachs webhook HMAC-SHA256 signing secret |
| `FREE_MONTHLY_CREDITS` | No | `50` | Free AI credits refreshed each calendar month |
| `CREDIT_PRICE_NGN` | No | `5` | ₦ per credit (used to calculate purchase amounts) |
| `MIN_PURCHASE_NGN` | No | `500` | Minimum credit purchase in Naira |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173` | Comma-separated CORS origins |
| `REDIS_URL` | No | — | Redis URL — cache disabled if blank |
| `ENV` | No | `development` | `development` \| `production` \| `test` |

---

## API Structure

All endpoints are versioned under `/api/v1/`.

### Auth — `/api/v1/auth/`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/signup` | — | Register; seeds Credential + Wallet; sends verification email |
| POST | `/login` | — | Returns access + refresh tokens |
| POST | `/refresh` | — | Rotate refresh token; returns new pair |
| POST | `/logout` | — | Revoke refresh token |
| GET | `/me` | Bearer | Authenticated user profile |
| PATCH | `/me/bvn` | Bearer | Submit BVN → flips `bvn_validated` claim |
| PATCH | `/me/phone` | Bearer | Save phone number |
| PATCH | `/me/address` | Bearer | Save address |
| POST | `/me/address/proof` | Bearer | Upload proof-of-address document (JPEG/PNG/PDF, 5 MB) |
| POST | `/me/avatar` | Bearer | Upload profile picture |
| PATCH | `/me/password` | Bearer | Change password |
| GET | `/me/identity-summary` | Bearer | Stream identity summary PDF |
| POST | `/forgot-password` | — | Send 6-digit OTP to email |
| POST | `/verify-reset-code` | — | Verify OTP → returns single-use reset token |
| POST | `/reset-password` | — | Set new password using reset token |
| POST | `/verify-email` | — | Verify email address using OTP |
| POST | `/resend-verification` | — | Re-send email verification OTP |

### Liveness — `/api/v1/auth/me/liveness/`

Server-side liveness ([faceliveness](https://pypi.org/project/faceliveness/)) + SFace face matching:

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/start` | Verified email | `{purpose: "enrol"\|"verify", consent}` → `{session_id, challenges, instructions, expires_at}`. Enrol requires `consent=true` |
| POST | `/{session_id}/frame` | Bearer | Raw `image/jpeg` body (320×240 recommended), one at a time (429 if overlapping) → `{status, done, current_challenge, remaining, fail_reason, face_count}` |
| POST | `/{session_id}/complete` | Verified email | Enrol: store encrypted template, flip `identity_verified`. Verify: 1:1 match → `{matched, score}` |
| GET | `/status` | Bearer | `{enrolled, verified_at, face_quality}` |
| GET | `/face` | Bearer | The user's own enrolled 112×112 face-record PNG |
| DELETE | `/enrolment` | Bearer | Delete template + face, reset `identity_verified` |

### Business platform (Open API)

FOID for fintechs: hosted, FOID-branded verification (NIN / BVN / liveness), server-to-server checks,
consent grants with revocation, signed webhooks, business dashboard API.

| Prefix | Auth | Router |
|---|---|---|
| `/api/open/v1/*` | `Bearer FOID_TEST_…` / `FOID_LIVE_…` | `routers/open_api.py` |
| `/api/v1/hosted/sessions/{token}/*` | session token in the URL (no login) | `routers/hosted.py` |
| `/api/v1/business/*` | FOID user JWT + org role | `routers/business.py` |
| `/api/v1/connected-apps` | FOID user JWT | `routers/connected_apps.py` |
| `/api/v1/admin/organisations` | admin | `routers/admin.py` (KYB → live mode) |

**Database setup.** The first Alembic revision is empty — base tables come from `init_db()` on
startup and migrations only upgrade existing databases. Fresh database: start the app once, then
`uv run alembic stamp head`. Existing database: `uv run alembic upgrade head`. Both SQLite and
Postgres are supported (datetimes go through `core/db_types.UTCDateTime`; tests run on either:
`FOID_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest`).

Guide: [`docs/open-api.md`](../docs/open-api.md) (developers).
Tests: `uv run pytest -q`.

### Credentials — `/api/v1/credentials/`

| Method | Path | Description |
|---|---|---|
| GET | `/me` | Get the user's FOID credential and claims |
| POST | `/trigger` | Apply a state-machine trigger event |

Trigger events: `missed_repayment`, `suspicious_activity`, `income_drop`, `review_cleared`,
`repayment_restored`, `appeal_approved`, `manual_revoke`

### Wallet — `/api/v1/wallet/`

| Method | Path | Description |
|---|---|---|
| GET | `` | Balance (free + paid) and transaction history |
| POST | `/initiate-purchase` | Create Bachs checkout session (min ₦500) |
| POST | `/bachs-webhook` | **Public** — Bachs payment webhook (HMAC-SHA256 verified) |
| POST | `/auto-topup` | Set / clear auto top-up threshold |

Credit pricing: ₦5 = 1 credit. 50 free credits every calendar month (lazy refresh).

### Ledger — `/api/v1/ledger/`

| Method | Path | Cost | Description |
|---|---|---|---|
| POST | `/upload` | 4 credits | Upload receipt → Groq OCR → LedgerEntry |
| POST | `/manual` | Free | Add manual ledger entry |
| GET | `` | Free | Paginated list with type/page filters |
| PATCH | `/{id}` | Free | Edit description, category, amount, type, date |
| DELETE | `/{id}` | Free | Delete an entry |
| POST | `/chat` | 1 credit | AI financial assistant (multi-turn) |
| GET | `/export/csv` | Free | Download all entries as CSV |
| GET | `/export/pdf` | Free | Download all entries as PDF |

### Reports — `/api/v1/reports/`

| Method | Path | Description |
|---|---|---|
| GET | `/summary` | Monthly income/expense/net/tax aggregates (JSON) |
| GET | `/export/csv` | Monthly summary as CSV |
| GET | `/export/pdf` | Full report PDF |
| GET | `/monthly-pdf` | Single-month audit PDF (`?month=YYYY-MM`) |

### Connected Banks — `/api/v1/banks/`

| Method | Path | Description |
|---|---|---|
| POST | `/exchange-token` | Exchange Mono Connect code → store bank connection |
| GET | `/connected` | List all connected bank accounts |
| POST | `/{id}/sync` | Re-fetch account details from Mono |
| DELETE | `/{id}` | Disconnect (remove) a bank |
| GET | `/{id}/transactions` | Proxy Mono transaction list |

### Notifications — `/api/v1/notifications/`

Credential state change notifications delivered to the user.

### Consents — `/api/v1/consents/`

Platform data access consent management (create / list / approve / revoke).

### Admin — `/api/v1/admin/` *(admin-only)*

| Method | Path | Description |
|---|---|---|
| GET | `/users` | List all users with verification flag summary |
| GET | `/users/{id}` | Full user profile + credential |
| PATCH | `/users/{id}/verifications` | Flip any verification flag on a user's credential claims |

---

## Database

### Dev (SQLite)

`foid.db` is created automatically at `backend/foid.db` on first start via `init_db()`.
No migration command needed in dev — tables are created/updated on startup.

### Production (PostgreSQL)

Set `DATABASE_URL=postgresql+asyncpg://...` and run:

```bash
uv run alembic upgrade head
```

After adding new columns: `uv run alembic stamp head` to sync the migration history
without re-running already-applied DDL.

### Tables

| Table | Description |
|---|---|
| `users` | First-party FOID accounts |
| `credentials` | One credential per user — state + claims JSON |
| `wallets` | Credit balance (free + paid buckets) |
| `wallet_transactions` | Append-only credit ledger |
| `ledger_entries` | Business income/expense entries |
| `connected_banks` | Mono-linked bank accounts |
| `consents` | Platform data access consents |
| `notifications` | Credential state change notifications |
| `refresh_tokens` | Rotating refresh tokens (SHA-256 hashed) |
| `email_verification_tokens` | 6-digit OTP tokens for email verification |
| `password_reset_tokens` | 6-digit OTP + single-use reset token for password reset |
| `face_enrolments` | One per user: Fernet-encrypted SFace template + exact face-record PNG + signed receipt |
| `used_liveness_nonces` | Accepted liveness receipt nonces (replay protection) |
| `liveness_attempts` | Audit of enrol/verify attempts (no images) |

---

## Liveness Check

Flow (`app/services/liveness_service.py`, `app/services/face_match_service.py`):

1. `/start` — the server issues a signed ticket (`SigningKey.issue_ticket`) that fixes the
   challenges (`turn_left`, `turn_right`, `open_mouth`; blink is excluded, unreliable with
   glasses). The ticket stays on the server; the client only gets the nonce + challenges.
2. `/frame` — each JPEG is decoded and fed to `Engine.process` with the **server clock**.
3. When done, the engine signs a receipt (Ed25519 JWT) holding the SHA-256 of the captured
   112×112 aligned face PNG.
4. `/complete` — `verify_face_record` (signature, expiry, passed, PNG hash) → reject reused
   nonce → reject quality < `FACE_MIN_QUALITY` → SFace embedding → enrol or cosine match
   against `FACE_MATCH_THRESHOLD`.

Env vars: `LIVENESS_SIGNING_KEY`, `FACE_TEMPLATE_KEY` (both **required in production**),
`LIVENESS_CHALLENGE_COUNT`, `FACE_MATCH_THRESHOLD`, `FACE_MIN_QUALITY`, `SFACE_MODEL_PATH`.
The SFace model (~37 MB) downloads on first start and is SHA-256 checked; the Docker image bakes it in.

> **Single worker only:** liveness sessions live in memory — run uvicorn with `--workers 1`.

> **Known limits:** passive anti-spoofing (`real_score`) is uncalibrated and report-only, so
> phone-screen replays are not reliably caught; no defence against deepfakes, virtual cameras
> or 3D masks; the match threshold has not been measured on FOID users yet.

---

## Background Tasks

A cleanup loop runs every 6 hours (started in the FastAPI `lifespan`) and deletes:
- Revoked or expired `refresh_tokens`
- Used or expired `password_reset_tokens`
- Used or expired `email_verification_tokens`

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `access_token` in memory only (never localStorage) | XSS cannot steal the short-lived token |
| Argon2id for passwords | Resistant to GPU/ASIC brute-force |
| Single `await db.commit()` per request | Atomicity — partial rows never written |
| `init_db()` on startup (dev) | Zero migration friction for development |
| `apply_monthly_refresh()` called lazily on wallet read | No cron needed — free credits reset on first use each month |
| Liveness engine on the server, not the device | A result computed on the device can be faked |
| Face templates Fernet-encrypted, deletable | Biometric data — NDPA 2023 |
| Bachs webhook verified with HMAC-SHA256 before processing | Credits never added without cryptographic proof of payment |
