"""'Continue with FOID' token endpoint — server to server, on the Open API.

POST /api/open/v1/oauth/token   (application/x-www-form-urlencoded or JSON)
  grant_type=authorization_code, code, code_verifier, redirect_uri (redirect mode only)
  client auth, one of:
    client_secret_basic   Authorization: Basic base64(client_id:client_secret)
    client_secret_post    client_id + client_secret in the body
    private_key_jwt       client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
                          client_assertion=<JWT signed with the app's key; iss=sub=client_id, aud=this URL, exp ≤ 5 min>
→ 200 the person's result (see services/oauth_flow.result), or an OAuth error {error, error_description}.
"""

from __future__ import annotations

import base64
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_db
from app.services import oauth_flow as of
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/open/v1/oauth", tags=["open-api"])

Db = Annotated[AsyncSession, Depends(get_db)]
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _basic(request: Request) -> tuple[str, str] | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return None
    try:
        cid, _, secret = base64.b64decode(auth[6:].strip()).decode().partition(":")
    except ValueError:
        return None
    return cid, secret


async def _form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").startswith("application/json"):
        data: Any = await request.json()
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    return {k: str(v) for k, v in (await request.form()).items()}


@router.post("/token")
@limiter.limit("60/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def token(request: Request, db: Db) -> JSONResponse:
    try:
        form = await _form(request)
        token_url = str(request.url).split("?")[0]
        app, secret = await of.authenticate_client(db, form, _basic(request), token_url)
        st = request.state   # so the call shows in the business's Request logs
        st.api_org_id, st.api_env, st.api_key_id, st.api_key_hint = app.org_id, app.env, None, app.client_id
        return JSONResponse(await of.exchange(db, app, secret, form), headers=_NO_STORE)
    except of.OAuthError as e:
        return JSONResponse({"error": e.error, "error_description": e.description}, status_code=e.status,
                            headers={**_NO_STORE, **({"WWW-Authenticate": "Basic"} if e.status == 401 else {})})
