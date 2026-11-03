"""The docs site's live "Continue with FOID" playground.

FOID owns one built-in **test** sign-in app ("FOID Docs playground"). The docs site renders the real
<ContinueWithFoid> button with it, and a developer can sign in to see the popup and the exact result a
business server receives.

Why a public exchange endpoint is safe here:
- it only exchanges codes for this one app (never a business's app);
- the code is useless without the PKCE code_verifier, which only the browser that started sign-in holds,
  so the result goes back to the person who just approved it in the popup;
- it's a test app: the real name only, everything else sandbox data;
- it is rate-limited, and switched off with DOCS_PLAYGROUND=false.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.models import Organisation
from app.models.oauth import OAuthApp
from app.services.consent_service import SCOPES

CLIENT_ID = "foid_app_test_docsplayground"
APP_NAME = "FOID Docs playground"


def _site() -> str:
    return get_settings().DOCS_SITE_URL.rstrip("/")


async def ensure_app(db: AsyncSession) -> OAuthApp:
    """The built-in app, created on first use and kept in sync with DOCS_SITE_URL."""
    app = (await db.exec(select(OAuthApp).where(OAuthApp.client_id == CLIENT_ID))).first()
    origins, redirects, scopes = [_site()], [f"{_site()}/playground"], list(SCOPES)
    if app is None:
        org = Organisation(name="FOID Docs", website=_site(), kyb_status="not_submitted")
        db.add(org)
        await db.flush()
        app = OAuthApp(org_id=org.id, env="test", name=APP_NAME, client_id=CLIENT_ID,
                       origins=origins, redirect_uris=redirects, scopes=scopes)
        db.add(app)
        await db.commit()
        await db.refresh(app)
    elif app.origins != origins or app.redirect_uris != redirects or app.scopes != scopes or app.disabled_at:
        app.origins, app.redirect_uris, app.scopes, app.disabled_at = origins, redirects, scopes, None
        db.add(app)
        await db.commit()
        await db.refresh(app)
    return app
