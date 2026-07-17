from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from loguru import logger
from core.config import settings
from core.session import init_db
from app import models
from app.routers import auth, user

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Event Handler"""

    await init_db()
    logger.info("Initialized datbase connection....")
    logger.info("Starting application...")
    yield
    logger.info("Shutting down application...")


# ----------- FastAPI Application Setup -------------- #
app = FastAPI(
    title="FOID — Fintech Open Identity API",
    description="API for fintech Auth",
    version="1.0.0",
    lifespan=lifespan,
)


# -----------middleware --------------#
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"],)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------Routes---------#
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(user.router, prefix=settings.API_PREFIX)

# ------health check endpoint-----#
@app.get("/")
async def root():
    return {
        "message": "Welcome to the FOID API!",
        "status": "Healthy"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)