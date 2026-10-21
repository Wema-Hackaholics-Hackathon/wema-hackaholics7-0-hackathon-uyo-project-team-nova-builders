#!/usr/bin/python3

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import check_db, get_settings, init_db
from .routers import *
from .utils.cache import ping as redis_ping
from .utils.limiter import limiter

_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60   # run every 6 hours


async def _token_cleanup_loop() -> None:
    """Background task: delete expired / used tokens every 6 hours."""
    from sqlalchemy import text
    from .config import _get_session_factory

    await asyncio.sleep(30)   # give the server a moment to fully start
    while True:
        try:
            now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            async with _get_session_factory()() as db:
                for stmt in (
                    "DELETE FROM refresh_tokens WHERE revoked = 1 OR expires_at < :now",
                    "DELETE FROM password_reset_tokens WHERE used = 1 OR expires_at < :now",
                    "DELETE FROM email_verification_tokens WHERE used = 1 OR expires_at < :now",
                ):
                    await db.execute(text(stmt), {"now": now_iso})
                await db.commit()
            print("[cleanup] expired tokens purged", flush=True)
        except Exception as exc:
            print(f"[cleanup] error: {exc}", flush=True)
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    db_ok = await check_db()
    redis_ok = await redis_ping()
    print(f"  Database : {'✓ connected' if db_ok else '✗ unreachable'}")
    print(f"  Redis    : {'✓ connected' if redis_ok else '✗ unreachable (cache disabled)'}")
    cleanup_task = asyncio.create_task(_token_cleanup_loop())
    yield
    cleanup_task.cancel()


settings = get_settings()

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # pyright: ignore[reportArgumentType]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root():
    return {"message": "Hello world"}


@app.get("/health")
async def health_check():
    """Health check endpoint for production monitoring."""
    ok = await check_db()
    if ok:
        return {"status": "healthy", "database": "connected"}
    return {"status": "unhealthy", "database": "unreachable"}


# ---------------------------------------------------------------------------
# API Version 1 Router — all feature routers attach here
# ---------------------------------------------------------------------------
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(admin_router)
v1_router.include_router(auth_router)
v1_router.include_router(banks_router)
v1_router.include_router(consents_router)
v1_router.include_router(credentials_router)
v1_router.include_router(ledger_router)
v1_router.include_router(liveness_router)
v1_router.include_router(notifications_router)
v1_router.include_router(reports_router)
v1_router.include_router(wallet_router)

app.include_router(v1_router)