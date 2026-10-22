![foid](image.png)

# FOID — Fintech Open Identity

> **Wema Hackaholics 7.0 Hackathon · Uyo · Team Nova Builders**

FOID is a reusable KYC and identity trust layer for the Nigerian fintech ecosystem.
A user verifies their identity once — FOID watches their Open Banking activity in real time and
automatically updates their financial trust credential the moment their behaviour changes.
No manual re-check ever needed. Any platform can integrate via our Open API.

---

## Team

| Name | GitHub |
|---|---|
| Wiseman Umanah | [@wiseman-umanah](https://github.com/wiseman-umanah) |
| Akwaubok Emeh | [@AHKAYY007](https://github.com/AHKAYY007) |
| Alex Daniel| [@AHKAYY007](https://github.com/TheCodeCheff123) |


---

## Live Links

| | URL |
|---|---|
| **Live Application** | *(deploy link)* |
| **Backend API** | *(API base URL)* |
| **Demo Video** | *(Loom link)* |

---

## The Problem

Nigerian fintechs re-run the same KYC and credit checks from scratch every time a customer
applies for a product — because there is no trusted, living identity layer shared between them.
This means higher onboarding costs, duplicate fraud checks, and a frustrating experience for
users who have already been verified elsewhere.

---

## Our Solution

FOID gives a user a **Verified Digital Credential** — a structured, tamper-evident record of
their identity and financial behaviour. The credential is backed by:

- **NIN + BVN verification** — official government and banking identity anchors
- **Active liveness check** — 3-challenge face detection (look left, open mouth, etc.) to
  prevent spoofing without any hardware dependency
- **Open Banking integration** — real transaction data from Mono-connected bank accounts feeds
  into account stability and repayment reliability signals
- **AI-powered business ledger** — OCR receipt scanning + Groq AI summarises income/expense
  patterns, giving an instant financial portrait

The credential **stays alive** — a state machine (active → under\_review → downgraded → revoked)
reacts to behavioural triggers (missed repayment, income drop, suspicious activity). Any platform
that has integrated FOID receives an instant webhook when a user's state changes.

---

## Platform Open API (B2B)

Fintechs and lenders integrate FOID with three API calls:

1. `POST /api/open/oauth/token` — mint a platform access token with `client_id` + `client_secret`
2. `POST /api/open/users` — register a user by email; FOID creates a linked user record
3. `GET /api/open/users/:id/credential` — read the user's verified claims filtered to your approved scopes

Face ID / liveness for your users — zero camera code required:

4. `POST /api/open/users/:id/liveness-request` — FOID returns a one-time URL; redirect your user to it
5. FOID hosts the liveness page, fires a webhook to your endpoint on pass

Users control their own data — a **Connected Apps** dashboard lets any FOID account holder
approve, inspect, and revoke platform access at any time.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS 4, Framer Motion, Recharts |
| **Backend** | Python 3.12, FastAPI, Uvicorn, SQLModel (SQLAlchemy 2 + Pydantic v2) |
| **AI / OCR** | Groq (Qwen + GPT-class models) — receipt parsing, financial chat |
| **Liveness** | OpenCV 4.10 — Haar cascade face/eye/smile detection, 3-challenge active check |
| **Open Banking** | Mono Connect — bank account linking, transaction history |
| **Payments** | Bachs — NGN credit purchase, webhook-verified top-up |
| **Database** | SQLite (dev) / PostgreSQL (prod) via aiosqlite / asyncpg |
| **Auth** | Argon2id password hashing, HS256 JWT access tokens, rotating refresh tokens |
| **Rate Limiting** | slowapi |
| **Cache** | Redis (optional — gracefully disabled if absent) |
| **PDF generation** | fpdf2 |

---

## Repository Structure

```
├── backend-2/          FastAPI backend (Python 3.12, uv)
│   ├── app/
│   │   ├── models/     SQLModel ORM tables
│   │   ├── routers/    API endpoint handlers
│   │   ├── schemas/    Pydantic request / response models
│   │   ├── services/   Business logic (Groq, Mono, Bachs, liveness, wallet)
│   │   ├── core/       JWT, password hashing, dependencies
│   │   ├── utils/      Rate limiter, Redis cache
│   │   └── data/       Haar cascade XML files
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/           React SPA (pnpm, Vite)
│   └── src/
│       ├── pages/      Landing, auth, dashboard pages
│       ├── components/ Reusable UI components
│       ├── contexts/   AuthContext, CredentialContext
│       └── lib/        axios API client
│
└── openbanking/        SSE event bridge (Python 3.12, FastAPI)
```

---

## Quick Start (Local)

### Backend

```bash
cd backend-2
cp .env.example .env          # fill in SECRET_KEY, GROQ_API_KEY, MONO_*, BACHS_*
uv sync
uv run uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
# → http://localhost:5173
```

### Docker (backend only)

```bash
cd backend-2
docker build -t foid-backend .
docker run -p 8000:8000 --env-file .env foid-backend
```

---

## API Reference

Interactive docs (Swagger UI): `http://localhost:8000/docs`
OpenAPI JSON: `http://localhost:8000/openapi.json`

All versioned endpoints are prefixed `/api/v1/`.
Platform Open API endpoints are prefixed `/api/open/`.

---

## Hackathon Context

Built for the **Wema Hackaholics 7.0 Hackathon**, Uyo track.
Challenge theme: turning a one-time Open Banking connection into an ongoing, automatically
trustworthy relationship between financial institutions and their customers.
