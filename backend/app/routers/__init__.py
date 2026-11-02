"""Entry point aggregating all FastAPI routers.

Import each router here and add it to ``__all__`` so that
``from .routers import *`` in main.py picks it up for registration.
"""

from .admin import router as admin_router
from .auth import router as auth_router
from .banks import router as banks_router
from .billing import router as billing_router
from .business import router as business_router
from .connected_apps import router as connected_apps_router
from .console_auth import router as console_auth_router
from .console_data import router as console_data_router
from .hosted import router as hosted_router
from .kyb import router as kyb_router
from .open_api import router as open_api_router
from .consents import router as consents_router
from .credentials import router as credentials_router
from .ledger import router as ledger_router
from .liveness import router as liveness_router
from .liveness_public import router as liveness_public_router
from .notifications import router as notifications_router
from .org_admin import public as invites_public_router
from .org_admin import router as org_admin_router
from .reports import router as reports_router
from .wallet import router as wallet_router

__all__ = [
    "admin_router",
    "auth_router",
    "banks_router",
    "billing_router",
    "business_router",
    "connected_apps_router",
    "console_auth_router",
    "console_data_router",
    "hosted_router",
    "kyb_router",
    "open_api_router",
    "consents_router",
    "credentials_router",
    "ledger_router",
    "liveness_router",
    "liveness_public_router",
    "notifications_router",
    "org_admin_router",
    "invites_public_router",
    "reports_router",
    "wallet_router",
]
