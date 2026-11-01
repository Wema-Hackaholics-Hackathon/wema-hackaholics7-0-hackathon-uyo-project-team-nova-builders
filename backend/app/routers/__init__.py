"""Entry point aggregating all FastAPI routers.

Import each router here and add it to ``__all__`` so that
``from .routers import *`` in main.py picks it up for registration.
"""

from .admin import router as admin_router
from .auth import router as auth_router
from .banks import router as banks_router
from .consents import router as consents_router
from .credentials import router as credentials_router
from .ledger import router as ledger_router
from .liveness import router as liveness_router
from .notifications import router as notifications_router
from .reports import router as reports_router
from .wallet import router as wallet_router

__all__ = [
    "admin_router",
    "auth_router",
    "banks_router",
    "consents_router",
    "credentials_router",
    "ledger_router",
    "liveness_router",
    "notifications_router",
    "reports_router",
    "wallet_router",
]
