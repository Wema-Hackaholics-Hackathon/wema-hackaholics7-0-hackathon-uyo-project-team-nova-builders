#!/usr/bin/python3

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import _get_engine, check_db, get_settings, init_db
from .core.schema_check import check_schema, has_table
from .core.api_errors import ApiError, api_error_handler
from .routers import *
from .services.webhook_service import webhook_loop
from .utils.cache import ping as redis_ping
from .utils.limiter import limiter

_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60   # run every 6 hours


async def _token_cleanup_loop() -> None:
    """Background task: purge expired tokens / stale accounts every 6 hours."""
    from .config import _get_session_factory
    from .services.maintenance_service import run_cleanup

    await asyncio.sleep(30)   # give the server a moment to fully start
    while True:
        try:
            async with _get_session_factory()() as db:
                counts = await run_cleanup(db)
            print(f"[cleanup] {counts}", flush=True)
        except Exception as exc:
            print(f"[cleanup] error: {exc}", flush=True)
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)


async def _liveness_sweep_loop() -> None:
    """Background task: drop abandoned in-memory liveness sessions every minute."""
    from .services.liveness_service import sweep_expired

    while True:
        await asyncio.sleep(60)
        removed = sweep_expired()
        from .services.liveness_handoff import sweep as sweep_handoffs
        sweep_handoffs()
        if removed:
            print(f"[liveness] swept {removed} expired session(s)", flush=True)
        try:
            from .config import _get_session_factory
            from .services.checks_service import expire_stale_verifications

            expired = await expire_stale_verifications(_get_session_factory())
            if expired:
                print(f"[verifications] expired {expired} unfinished verification(s)", flush=True)
        except Exception as exc:
            print(f"[verifications] expiry error: {exc}", flush=True)


async def _warm_liveness() -> None:
    """Load the signing key and SFace model up front so the first check isn't slow."""
    from starlette.concurrency import run_in_threadpool
    from .services.face_match_service import ensure_sface_model
    from .services.liveness_service import get_signing_key

    get_signing_key()
    try:
        path = await run_in_threadpool(ensure_sface_model)
        print(f"  SFace    : ✓ {path}", flush=True)
    except Exception as exc:
        if get_settings().ENV == "production":
            raise
        print(f"  SFace    : ✗ {exc} (face matching unavailable)", flush=True)


async def _enable_wal_mode() -> None:
    """Enable SQLite WAL journal mode.

    WAL allows concurrent readers + one writer, eliminating 'database is locked'
    errors that occur when the background cleanup task and a request handler try
    to write at the same time under the default DELETE journal mode.
    Only runs for SQLite databases — silently skipped otherwise.
    """
    from sqlalchemy import text
    from .config import _get_session_factory, get_settings

    if not get_settings().DATABASE_URL.startswith("sqlite"):
        return
    async with _get_session_factory()() as db:
        await db.execute(text("PRAGMA journal_mode=WAL"))
        await db.execute(text("PRAGMA synchronous=NORMAL"))
        await db.commit()
    print("  SQLite   : WAL journal mode enabled", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine = _get_engine()
    was_empty = not await has_table(engine, "users")
    if was_empty:
        # Brand-new database: create every table at the current schema (then stamped at head).
        # An existing database is left to Alembic — creating new tables here would make the
        # next `alembic upgrade head` fail with "table already exists".
        await init_db()
    await _enable_wal_mode()
    schema = await check_schema(engine, was_empty=was_empty)
    _app.state.schema_error = schema.message
    db_ok = await check_db()
    redis_ok = await redis_ping()
    print(f"  Database : {'✓ connected' if db_ok else '✗ unreachable'} ({get_settings().DATABASE_URL})")
    if schema.ok:
        print(f"  Schema   : ✓ {schema.db_revision}")
    else:
        print("\n" + "!" * 78 + f"\n  {schema.message}\n  API requests will return 503 until this is done.\n" + "!" * 78 + "\n",
              flush=True)
    print(f"  Redis    : {'✓ connected' if redis_ok else '✗ unreachable (cache disabled)'}")
    await _warm_liveness()
    cleanup_task = asyncio.create_task(_token_cleanup_loop())
    sweep_task = asyncio.create_task(_liveness_sweep_loop())
    webhook_task = asyncio.create_task(webhook_loop())
    yield
    cleanup_task.cancel()
    sweep_task.cancel()
    webhook_task.cancel()


settings = get_settings()

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # pyright: ignore[reportArgumentType]
)

app.state.schema_error = None


@app.middleware("http")
async def schema_guard(request: Request, call_next):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    """Un-migrated database → clear 503 instead of opaque 500s (see core/schema_check.py).

    Registered before CORS, so the 503 still carries CORS headers and the
    browser shows the message instead of a network error.
    """
    message = getattr(request.app.state, "schema_error", None)
    if message and request.url.path.startswith("/api"):
        return JSONResponse(status_code=503, content={"detail": message})
    return await call_next(request)


# Open API calls: FOID-Request-Id header + request log for the business console
from .services import request_log_service  # noqa: E402

app.middleware("http")(request_log_service.middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "FOID-Request-Id"],   # CSV filenames, request IDs
)


@app.get("/")
async def read_root():
    return {"message": "Hello world"}


@app.get("/health")
async def health_check():
    """Health check endpoint for production monitoring."""
    ok = await check_db()
    schema_error = getattr(app.state, "schema_error", None)
    if ok and not schema_error:
        return {"status": "healthy", "database": "connected", "schema": "up to date"}
    return {"status": "unhealthy", "database": "connected" if ok else "unreachable",
            "schema": schema_error or "unknown"}


# ---------------------------------------------------------------------------
# API Version 1 Router — all feature routers attach here
# ---------------------------------------------------------------------------
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(admin_router)
v1_router.include_router(auth_router)
v1_router.include_router(account_security_router)
v1_router.include_router(banks_router)
v1_router.include_router(business_router)
v1_router.include_router(kyb_router)
v1_router.include_router(console_data_router)
v1_router.include_router(billing_router)
v1_router.include_router(org_admin_router)
v1_router.include_router(invites_public_router)
v1_router.include_router(connected_apps_router)
v1_router.include_router(console_auth_router)
v1_router.include_router(hosted_router)
v1_router.include_router(consents_router)
v1_router.include_router(credentials_router)
v1_router.include_router(ledger_router)
v1_router.include_router(liveness_router)
v1_router.include_router(liveness_public_router)
v1_router.include_router(notifications_router)
v1_router.include_router(reports_router)
v1_router.include_router(wallet_router)

app.include_router(v1_router)
app.include_router(open_api_router)   # public business API: /api/open/v1/*