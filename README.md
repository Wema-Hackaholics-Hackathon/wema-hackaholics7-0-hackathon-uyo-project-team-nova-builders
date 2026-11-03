![foid](image.png)

# FOID — Fintech Open Identity

> **Wema Hackaholics 7.0 Hackathon · Uyo · Team Nova Builders**

FOID is a reusable identity layer for Nigerian fintech. A person verifies once — NIN, BVN and a live
face check — and shares that proof with banks and apps **only when they approve**, revoking access
whenever they like. The credential stays alive: connected Open Banking activity can move it between
`active → under_review → downgraded → revoked`, and every business holding it is told.

Businesses integrate through an Open API, a hosted verification page, or a **Continue with FOID**
sign-in button, with SDKs for Python, Node and React.

---

## Team

| Name | GitHub |
|---|---|
| Wiseman Umanah | [@wiseman-umanah](https://github.com/wiseman-umanah) |
| Akwaubok Emeh | [@AHKAYY007](https://github.com/AHKAYY007) |
| Alex Daniel| [@TheCodeCheff123](https://github.com/TheCodeCheff123) |


---

## Live Links

| | URL |
|---|---|
| **Live Application** | *(deploy link)* |
| **Backend API** | *(API base URL)* |
| **Demo Video** | *(Loom link)* |

---

## What's in this repo

| App | Folder | Stack | Port | Who it's for |
|---|---|---|---|---|
| **Backend** | `backend/` | Python 3.12, FastAPI, SQLModel, Alembic | **8000** | Everything: user API, console API, Open API, sign-in, webhooks |
| **User app** | `frontend/` | React 19, Vite, Tailwind 4 | **5173** | People: create and verify a FOID, share it, manage consent. Also hosts the hosted-verification page and the *Continue with FOID* popup |
| **Business console** | `enterprise/` | React 19, Vite, Tailwind 4 | **5174** | Businesses: API keys, sign-in apps, webhooks, request logs, team, billing, go-live (KYB) |
| **Docs** | `docs/` | VitePress | **5177** | Developer guides, SDK docs, API reference, live playground, user help centre |
| **SDKs** | `sdks/` | Python, Node, React | — | `foid`, `@foid/node`, `@foid/react` |
| **Example app** | `demo/` | Docker (React + Python or Node) | **3100 / 3200** | "Harbor", a pretend business that uses every SDK feature |
| *Open Banking prototype* | `openbanking/` | FastAPI | — | Standalone early prototype. **Not used** by the apps above — don't run it |

```
FOID/
├── backend/          FastAPI app (app/), Alembic migrations, tests, Dockerfile
│   └── app/          routers/ services/ models/ schemas/ core/ config/ utils/ data/
├── frontend/         FOID user app
├── enterprise/       business console
├── docs/             docs site (help/, guide/, sdks/, api/, playground)
├── sdks/             python/ node/ react/
├── demo/             Harbor example app (docker compose up python | node)
└── openbanking/      standalone prototype (not wired in)
```

---

## Run everything with Docker (quickest way to try FOID)

All you need is [Docker](https://docs.docker.com/get-docker/). From the repo root:

```bash
docker compose up --build        # first run: a few minutes to build; later runs start in seconds
```

| Open | What | Sign in with |
|---|---|---|
| http://localhost:5173 | FOID user app | `ada@example.com` / `FoidTester#2026` |
| http://localhost:5174 | Business console | `demo@harbor.example` / `HarborDemo#2026` |
| http://localhost:5177 | Docs, playground, help centre | — |
| http://localhost:3100 · http://localhost:3200 | Harbor demo (Python / Node backend) | — |
| http://localhost:8000/docs | FOID API (Swagger) · `/mcp` docs MCP server | — |

On first boot the backend creates a **test** business with an API key, a sign-in app and webhooks for the
demo, plus a FOID user — so the demo works straight away. Everything is test mode (sandbox data).

- **Codes:** sign-in and verification codes are emailed — with no email service set up they're printed in
  the logs: `docker compose logs -f backend`.
- **Optional services** (real email, AI chat, Mono, Bachs): copy `.env.example` (repo root) to `.env` and fill in.
- **Stop:** `docker compose down`. **Start over** with a fresh database: `docker compose down -v`.
- The ports above must be free — stop any `pnpm dev` / `uvicorn` you're running for FOID first.

## First-time setup (without Docker)

You need **Python 3.12 + [uv](https://docs.astral.sh/uv/)**, **Node 18+ + [pnpm](https://pnpm.io)**, and **Docker** (only for the example app).

```bash
# Backend
cd backend
cp .env.example .env            # works as is for local dev — see the comments inside
uv sync
uv run alembic upgrade head     # a brand-new database is created automatically; this keeps an existing one up to date

# Front ends
cd ../frontend   && pnpm install
cd ../enterprise && pnpm install
cd ../docs       && pnpm install
```

Every external service (email, AI, Mono, Bachs, Redis) is optional — with the keys blank the app still runs, and **emails are printed in the backend terminal** (that's where you'll find sign-up and sign-in codes locally).

## Run it

One terminal per app:

```bash
cd backend    && uv run uvicorn app.main:app --reload   # http://localhost:8000  (API docs: /docs)
cd frontend   && pnpm dev                               # http://localhost:5173
cd enterprise && pnpm dev                               # http://localhost:5174
cd docs       && pnpm dev                               # http://localhost:5177
```

What you need for what:

| To… | Run |
|---|---|
| Use FOID as a person (sign up, verify, share, revoke) | backend + frontend |
| Manage a business (keys, sign-in apps, webhooks) | backend + enterprise |
| Try **Continue with FOID** or a hosted verification | backend + frontend (the popup and verification pages live there) |
| Read the docs | docs (the playground also needs backend + frontend) |
| Run the Harbor example app | backend + frontend + enterprise (to create its keys), then `cd demo && docker compose up python --build` — see [demo/README.md](demo/README.md) |

After pulling changes, run `uv sync` and `uv run alembic upgrade head` in `backend/` again. If the
database is behind, the API answers **503** with the exact command to run.

## Tests

```bash
cd backend && uv run pytest -q          # throwaway SQLite; never touches your foid.db or real services
```

To run against Postgres: `FOID_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest -q`.
The front ends have no test runner; `pnpm build` type-checks them.

## Environment files

Each app has a `.env.example` explaining every variable. Copy it, never commit the real file.

| App | Copy to | Notes |
|---|---|---|
| `backend/.env.example` | `backend/.env` | Core settings, keys required in production, optional external services |
| `frontend/.env.example` | `frontend/.env.local` | API URL, Mono public key, docs URL |
| `enterprise/.env.example` | `enterprise/.env.local` | API URL, docs URL |
| `docs/.env.example` | `docs/.env` | Only for deploying the docs site |
| `demo/.env.example` | `demo/.env` | Keys you create in the console for the example app |

## SDKs and docs

- **Docs site** — `docs/` ([how to run it](docs/README.md)): quickstart, guides, SDK reference, an API reference generated from the backend, a live *Continue with FOID* playground and the user help centre. AI-friendly too: `llms.txt`, a *Copy page* menu on every page, and a docs MCP server on the backend (`/mcp`) — see the *Use FOID docs with AI* page.
- **SDKs** — [sdks/README.md](sdks/README.md): `foid` (Python) and `@foid/node` for servers, `@foid/react` for the browser.
- **Example app** — [demo/README.md](demo/README.md): Harbor, in Docker, with a Python or Node backend.

## Tech stack

| Layer | Technology |
|---|---|
| **Front ends** | React 19, TypeScript, Vite, Tailwind CSS 4, Framer Motion, Recharts |
| **Backend** | Python 3.12, FastAPI, Uvicorn, SQLModel (SQLAlchemy 2 + Pydantic v2), Alembic |
| **Database** | SQLite (dev) / PostgreSQL (prod) via aiosqlite / asyncpg |
| **Identity** | NIN/BVN lookups behind a provider interface (sandbox mock in test mode) |
| **Liveness** | [faceliveness](https://pypi.org/project/faceliveness/) (server-side, Ed25519-signed receipts) + OpenCV SFace for 1:1 face matching |
| **Sign-in for businesses** | OAuth 2.0 authorization code + PKCE, client secret or `private_key_jwt` |
| **Auth** | Argon2id passwords, HS256 JWT + rotating refresh tokens, TOTP two-factor, passkeys (WebAuthn) |
| **AI / OCR** | Groq — in-app assistant, NIN document reading, receipt parsing |
| **Open Banking** | Mono Connect |
| **Payments** | Bachs |
| **Email** | Resend (printed to the terminal when not configured) |
| **Docs** | VitePress |
| **Other** | slowapi (rate limits), Redis (optional cache), fpdf2 (PDFs) |

## Deploying the backend with Docker

```bash
docker build -f backend/Dockerfile -t foid-backend .     # from the repo root
docker run -p 8000:8000 --env-file backend/.env foid-backend
```

Set `ENV=production` and every key marked *REQUIRED IN PRODUCTION* in `backend/.env.example`.

---

## Hackathon Context

Built for the **Wema Hackaholics 7.0 Hackathon**, Uyo track.
Challenge theme: turning a one-time Open Banking connection into an ongoing, automatically
trustworthy relationship between financial institutions and their customers.
