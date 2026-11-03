# FOID Backend

FastAPI backend for FOID — one API serving the FOID user app (`frontend/`), the business console
(`enterprise/`), the public Open API for businesses, the *Continue with FOID* sign-in flow, hosted
verification, webhooks and the docs site's playground.

## Stack

| Package | Purpose |
|---|---|
| **FastAPI + Uvicorn** | Async HTTP server |
| **SQLModel** (SQLAlchemy 2 + Pydantic v2) | ORM — models are both DB tables and Pydantic schemas |
| **aiosqlite / asyncpg** | SQLite (dev) and PostgreSQL (prod) async drivers |
| **Alembic** | Database migrations |
| **argon2-cffi** | Password hashing (Argon2id) |
| **python-jose** | HS256 JWTs; ES256/RS256 client assertions (`private_key_jwt`) |
| **webauthn** | Passkeys ("Biometric unlock") |
| **faceliveness** | Server-side active liveness (head turns / mouth), signed Ed25519 receipts |
| **OpenCV + SFace** | JPEG frame decode; SFace (Apache-2.0) embeddings for 1:1 face matching |
| **Groq** | AI chat, receipt OCR, NIN document reading |
| **httpx** | Mono, Bachs, Resend and webhook deliveries |
| **fpdf2** | PDF reports and identity summary |
| **slowapi** | Rate limiting |
| **Redis** | Optional cache — disabled if `REDIS_URL` is blank |

## Setup

```bash
cd backend                       # always run from here — the app is app.main:app
cp .env.example .env             # works as is for local dev; every variable is explained inside
uv sync
uv run alembic upgrade head
```

Nothing external is required locally. With `RESEND_API_KEY` blank, every email (sign-up codes,
sign-in codes, alerts) is **printed to this terminal**.

## Running

```bash
uv run uvicorn app.main:app --reload      # or: uv run foid-dev
```

| URL | Purpose |
|---|---|
| `http://localhost:8000/docs` | Swagger UI (every route, including internal ones) |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/health` | Health check: database + schema status |
| `http://localhost:8000/openapi.json` | Raw OpenAPI spec |

The public developer reference lives in the docs site (`docs/api/reference.md`, generated from this
app with `cd docs && pnpm api`).

> **Single worker only:** liveness sessions live in memory — run uvicorn with `--workers 1`.

## Database and migrations

- **Brand-new database:** on first start the app creates every table at the current schema and
  stamps it at the Alembic head. Nothing to run.
- **Existing database:** run `uv run alembic upgrade head` after pulling. If you forget, the API
  answers **503** with that exact command (and prints it on startup).
- **New migration:** `uv run alembic revision -m "describe it"`, write `upgrade()`/`downgrade()`,
  then `uv run alembic upgrade head`.
- SQLite and PostgreSQL are both supported. Datetimes go through `core/db_types.UTCDateTime`
  (stored as naive UTC).

## Tests

```bash
uv run pytest -q                                  # throwaway SQLite, external services blanked
FOID_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest -q   # same suite on Postgres
```

Tests never touch `foid.db` or real external services (email, Groq, Mono, Bachs, DNS).

## Docker

Build from the **repo root** (the image also copies the email logo from `frontend/public`):

```bash
docker build -f backend/Dockerfile -t foid-backend .
docker run -p 8000:8000 --env-file backend/.env foid-backend
```

The image bakes in the SFace model. For production set `ENV=production`, a Postgres
`DATABASE_URL`, and every key marked *REQUIRED IN PRODUCTION* in `.env.example`.

## Configuration

All settings live in `app/config/__init__.py` (`Settings`, pydantic-settings) and are documented
one by one in [`.env.example`](.env.example). New settings go there too.

## API map

| Prefix | Auth | Routers | For |
|---|---|---|---|
| `/api/v1/auth/*` | none / user JWT | `auth.py`, `account_security.py` | Sign-up, login (+ 2FA, passkeys), profile, NIN/BVN, password, security settings |
| `/api/v1/auth/me/liveness/*`, `/api/v1/liveness/*` | user JWT / one-time link | `liveness.py`, `liveness_public.py` | Face check (enrol / verify), continue-on-phone handoff |
| `/api/v1/credentials/*` | user JWT / public token | `credentials.py` | The user's credential, FOID code (`/me/code`, public `/code/{token}`) |
| `/api/v1/connected-apps`, `/api/v1/consents` | user JWT | `connected_apps.py`, `consents.py` | Who the user shares with; revoke |
| `/api/v1/banks`, `/ledger`, `/reports`, `/wallet`, `/notifications` | user JWT | | Mono banks, ledger + AI chat, reports, AI credit wallet, notifications |
| `/api/v1/console/auth/*`, `/api/v1/console/invites/*` | none / console JWT | `console_auth.py`, `org_admin.py` | Business console accounts, invitations |
| `/api/v1/business/*` | console JWT + org role | `business.py`, `oauth_apps.py`, `console_data.py`, `kyb.py`, `billing.py`, `org_admin.py` | API keys, sign-in apps, webhooks, logs, KYB, billing, team |
| `/api/v1/hosted/sessions/{token}/*` | session token in URL | `hosted.py` | Hosted verification page |
| `/api/v1/oauth/*` | none / user JWT | `oauth.py` | *Continue with FOID* popup (email code, consent, guest flow, Save to FOID) |
| `/api/v1/docs-playground/*` | none | `docs_playground.py` | Docs site playground (one built-in test app; `DOCS_PLAYGROUND=false` turns it off) |
| `/api/v1/admin/*` | admin | `admin.py` | FOID staff: users, KYB review, live mode |
| `/api/open/v1/*` | `Bearer FOID_TEST_…` / `FOID_LIVE_…` | `open_api.py` | **Open API** for businesses: verifications, checks, subjects |
| `/api/open/v1/oauth/token` | client secret or `private_key_jwt` | `oauth_token.py` | *Continue with FOID* code exchange |

Rules that hold everywhere:

- Every read of a person's data for a business goes through `services/consent_service.py`:
  revoked consent → `403 consent_revoked`, and queued webhooks about that person are cancelled.
- Raw NIN/BVN are never stored for business subjects — keyed hash (`core/crypto.pii_hash`) + last 4.
- Open API errors use one shape: `{"error": {"type", "code", "message", "param"}}` (`core/api_errors.py`).
- Webhook URLs are checked when saved and at every delivery (`services/webhook_urls.py`): https only
  in live, no private/internal addresses, no redirects, connection pinned to the checked IP.

## Liveness and face matching

`services/liveness_service.py`, `services/face_match_service.py`:

1. `/start` — the server issues a signed ticket that fixes the challenges (`turn_left`, `turn_right`,
   `open_mouth`). The ticket stays on the server; the client only gets the nonce and challenges.
2. `/frame` — each JPEG is decoded and fed to the engine with the **server clock**.
3. When done, the engine signs a receipt (Ed25519) holding the SHA-256 of the 112×112 face PNG.
4. `/complete` — verify the receipt → reject a reused nonce → reject low quality → SFace embedding →
   enrol (template Fernet-encrypted) or cosine match against `FACE_MATCH_THRESHOLD`.

The SFace model (~37 MB) downloads on first start and is SHA-256 checked.

**Known limits:** passive anti-spoofing (`real_score`) is uncalibrated and report-only, so phone-screen
replays aren't reliably caught; no defence against deepfakes, virtual cameras or 3D masks; the match
threshold hasn't been measured on FOID users.

## Background tasks

Started in the FastAPI `lifespan` (`main.py`):

| Loop | Every | Does |
|---|---|---|
| Cleanup (`services/maintenance_service.py`) | 6 hours | Purges expired tokens and codes, idempotency records (24 h), old *Continue with FOID* requests, console notifications, request logs (30 days); deletes accounts whose email wasn't verified within 3 days and organisations deactivated for 30 days; opens renewal invoices |
| Liveness sweep | 60 s | Drops stale in-memory liveness sessions; expires old hosted verifications |
| Webhooks (`services/webhook_service.py`) | continuous | Delivers queued webhook events with retries and backoff |

## Key design decisions

| Decision | Rationale |
|---|---|
| Access token in memory only (never localStorage); refresh token rotates | XSS can't steal the short-lived token |
| Argon2id passwords; TOTP 2FA; passkeys | Strong sign-in without SMS |
| Liveness engine on the server, not the device | A result computed on the device can be faked |
| Face templates Fernet-encrypted, deletable | Biometric data — NDPA 2023 |
| PKCE required for every sign-in app; codes single use, 60 s; replay revokes | OAuth 2.1 / security BCP |
| Separate client secret (or key pair) from the API key | A leaked sign-in secret can't read every customer |
| Test mode returns sandbox data (except the signed-in person's real name) | Developers learn the shapes without touching real identities |
| Webhook bodies signed (HMAC-SHA256, `FOID-Signature`) | Businesses can prove an event came from FOID |
