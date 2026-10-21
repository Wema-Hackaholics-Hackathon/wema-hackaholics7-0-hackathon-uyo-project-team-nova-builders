# FOID Backend

FastAPI backend for the FOID Identity & Digital Risk Assessment platform.

## Stack

- **Python 3.12**, FastAPI, Uvicorn
- **SQLModel** (SQLAlchemy 2 + Pydantic) — ORM
- **Alembic** — database migrations
- **SQLite** for local dev, **PostgreSQL** for production
- **Groq** — AI receipt parsing & chat
- **Mono** — Open Banking (account linking)
- **Paystack** — payment processing (AI credit purchases)
- **slowapi** — rate limiting
- **Redis** — optional response cache (gracefully disabled if absent)

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — the project uses `uv` as its package manager

## Setup

```bash
# 1. Clone and enter the backend directory
cd backend

# 2. Install all dependencies (uv reads pyproject.toml + uv.lock)
uv sync

# 3. Copy the environment file and fill in your keys
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY, GROQ_API_KEY, MONO_*, PAYSTACK_*

# 4. Apply database migrations (creates idra.db for SQLite dev)
uv run alembic upgrade head
```

## Running the Dev Server

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs  
Health check: http://localhost:8000/health

## Database Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration after changing models
uv run alembic revision --autogenerate -m "describe your change"

# Downgrade one step
uv run alembic downgrade -1
```

> **Important:** Always run Alembic commands from the `backend/` directory.  
> The `alembic.ini` file must be in the working directory.

## Running Tests

```bash
# All tests
uv run pytest

# Single test
uv run pytest tests/path/test_file.py::test_function_name -v
```

## Environment Variables

See [`.env.example`](.env.example) for the full list with descriptions.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./idra.db` |
| `SECRET_KEY` | **Yes** | JWT signing key — must be strong and secret |
| `GROQ_API_KEY` | **Yes** | Groq API key for AI ledger features |
| `MONO_PUBLIC_KEY` | **Yes** | Mono Connect public key |
| `MONO_SECRET_KEY` | **Yes** | Mono server-side secret key |
| `PAYSTACK_SECRET_KEY` | **Yes** | Paystack secret key for payment + webhooks |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (default: `http://localhost:5173`) |
| `REDIS_URL` | No | Redis connection URL — leave blank to disable caching |

## Mono Connect Flow

The frontend opens the Mono Connect widget (JS SDK) which generates a one-time `code` on success.  
The frontend POSTs this code to `POST /api/v1/banks/exchange-token`.  
The backend exchanges it with Mono's API for a permanent `accountId`, then stores the bank connection.

## Paystack Webhook

The `POST /api/v1/wallet/paystack-webhook` endpoint is **public** (no JWT required).  
It verifies the `x-paystack-signature` HMAC-SHA512 header before processing any event.  
Credits are added to the user's wallet **only after** a `charge.success` event is verified.

## API Prefix

All versioned endpoints are under `/api/v1`. Example:
- `POST /api/v1/auth/signup`
- `GET  /api/v1/credentials/me`
- `POST /api/v1/ledger/upload`
