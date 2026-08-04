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
from app.routers import auth, user, kyc

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter
from slowapi.middleware import SlowAPIMiddleware


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
    description="""FOID (Fintech Open Identity) is a portable, user-centric financial identity 
    platform designed to revolutionize how individuals interact with fintech services, loan apps, 
    and traditional banks. By allowing users to complete a rigorous KYC (Know Your Customer) 
    process just once, FOID provides a reusable digital identity credential. Users can securely 
    connect multiple bank accounts via Open Banking, centralize their financial data, and use a 
    frictionless "Verify with FOID" single sign-on mechanism to authenticate themselves on 
    third-party platforms. Instead of administrative bloat, the FOID dashboard is explicitly centered
    around the user's financial identity, consent management, and daily interactions, augmented by advanced 
    AI functionalities for bookkeeping and insights.""",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# -----------middleware --------------#
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"],)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(SlowAPIMiddleware)
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
app.include_router(kyc.router, prefix=settings.API_PREFIX)

# ------health check endpoint-----#
@app.get("/")
async def root():
    return {
        "message": "Welcome to the FOID API!",
        "status": "Healthy"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)