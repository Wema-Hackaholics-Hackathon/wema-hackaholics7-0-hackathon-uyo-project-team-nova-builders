"""Bootstrap configuration objects shared across the backend."""

from functools import lru_cache
from typing import ClassVar, Literal

import sqlalchemy
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./foid.db"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # External APIs
    GROQ_API_KEY: str = ""
    MONO_SECRET_KEY: str = ""
    MONO_PUBLIC_KEY: str = ""

    # Email — Resend (https://resend.com)
    # If RESEND_API_KEY is set, emails are sent via Resend regardless of ENV.
    # If blank, all emails are printed to the terminal (dev console mode).
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "FOID <onboarding@resend.dev>"   # override with your verified domain

    # Bachs payment provider
    BACHS_API_KEY: str = ""             # sk_sandbox_... or sk_live_...
    BACHS_WEBHOOK_SECRET: str = ""      # from Bachs Developer Portal

    # AI Credit wallet
    FREE_MONTHLY_CREDITS: int = 50          # free credits refreshed every calendar month
    CREDIT_PRICE_NGN: int = 5               # ₦5 per credit
    MIN_PURCHASE_NGN: int = 500             # minimum purchase amount

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Redis (optional — cache is disabled gracefully if not set)
    REDIS_URL: str = ""

    # Environment
    ENV: Literal["development", "production", "test"] = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Database engine & session factory
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if settings.DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.ENV == "development",
            connect_args=connect_args,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,  # SQLModel's AsyncSession, which has .exec()
            expire_on_commit=False,
        )
    return _session_factory


async def get_db():
    """FastAPI dependency — yields an AsyncSession and closes it after the request."""
    async with _get_session_factory()() as session:
        yield session


async def init_db() -> None:
    """Create all tables on startup (dev convenience; production uses Alembic)."""
    async with _get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def check_db() -> bool:
    """Ping the database; returns True if reachable."""
    try:
        async with _get_engine().connect() as conn:
            _ = await conn.execute(sqlalchemy.text("SELECT 1"))
        return True
    except Exception:
        return False
