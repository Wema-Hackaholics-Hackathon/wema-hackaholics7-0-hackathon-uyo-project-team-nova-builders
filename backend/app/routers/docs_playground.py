"""Docs site playground: GET /api/v1/docs-playground/config, POST /api/v1/docs-playground/exchange.

See services/docs_playground.py for why this is safe to leave public.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db, get_settings
from app.core.api_errors import ApiError
from app.services import docs_playground as dp
from app.services import oauth_flow as of
from app.services.consent_service import SCOPES
from app.utils.limiter import limiter

router = APIRouter(prefix="/docs-playground", tags=["docs"])
Db = Annotated[AsyncSession, Depends(get_db)]
_NO_STORE = {"Cache-Control": "no-store"}


def _enabled() -> None:
    if not get_settings().DOCS_PLAYGROUND:
        raise ApiError(404, "not_found", "The docs playground is switched off on this server")


class ExchangeBody(BaseModel):
    code: str = Field(max_length=200)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str | None = Field(default=None, max_length=500)


@router.get("/config")
async def config(db: Db) -> dict[str, Any]:
    _enabled()
    app = await dp.ensure_app(db)
    return {"client_id": app.client_id, "foid_url": get_settings().PUBLIC_APP_URL.rstrip("/"),
            "scopes": {s: SCOPES[s] for s in app.scopes}}


@router.post("/exchange")
@limiter.limit("20/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def exchange(request: Request, body: ExchangeBody, db: Db) -> JSONResponse:
    """What a business server gets from POST /api/open/v1/oauth/token — for the playground app only."""
    _enabled()
    app = await dp.ensure_app(db)
    form = {"grant_type": "authorization_code", "code": body.code, "code_verifier": body.code_verifier,
            **({"redirect_uri": body.redirect_uri} if body.redirect_uri else {})}
    try:
        return JSONResponse(await of.exchange(db, app, None, form), headers=_NO_STORE)
    except of.OAuthError as e:
        return JSONResponse({"error": e.error, "error_description": e.description}, status_code=e.status,
                            headers=_NO_STORE)
