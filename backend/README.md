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
| **OpenCV 4.10** | Active liveness challenge detection (Haar cascades) |
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
cd backend-2

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
cd backend-2
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
cd backend-2
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

3-step active challenge flow (face detection via OpenCV):

| Method | Path | Description |
|---|---|---|
| POST | `/start` | Create session; returns 3 random challenges |
| POST | `/ping` | Lightweight face-detection probe (no DB write) |
| POST | `/verify` | Submit one challenge frame |
| POST | `/complete` | Finalise session → flips `identity_verified`, saves selfie |

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

`foid.db` is created automatically at `backend-2/foid.db` on first start via `init_db()`.
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
| `liveness_sessions` | Active challenge sessions (TTL 10 minutes) |

---

## Liveness Check

Challenges: `look_left`, `look_right`, `look_up`, `look_down`, `open_mouth`

Each session issues 3 random challenges. OpenCV 4.10 Haar cascade classifiers
(`haarcascade_frontalface_default.xml`, `haarcascade_eye.xml`, `haarcascade_smile.xml`)
are bundled in `app/data/cascades/`.

> **Note:** OpenCV 5.x removed `CascadeClassifier` — the project pins `opencv-python-headless==4.10.0.84`.

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
| OpenCV 4.10 pinned | 5.x removed CascadeClassifier |
| Bachs webhook verified with HMAC-SHA256 before processing | Credits never added without cryptographic proof of payment |
