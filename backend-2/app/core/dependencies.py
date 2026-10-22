"""FastAPI dependencies shared across routers.

Import ``get_current_user`` in any route that requires authentication.
Import ``require_verified_email`` on any mutation route that should be blocked
for users who have not yet confirmed their email address.

    from app.core.dependencies import get_current_user, require_verified_email

    @router.post("/something")
    async def do_something(
        current_user: Annotated[User, Depends(require_verified_email)],
        ...
    ):
        ...
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession  # has .exec() unlike sqlalchemy's AsyncSession

from app.config import get_db
from app.core.security import decode_access_token
from app.models import Credential, User

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Decode the Bearer token and return the matching User row.

    Raises HTTP 401 if the token is missing, invalid, or the user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(credentials.credentials)
    except JWTError:
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user


async def require_verified_email(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extend get_current_user — additionally raise HTTP 403 if the user's
    email address has not been verified yet.

    Use this instead of get_current_user on any route that mutates data or
    consumes credits.  Read-only profile endpoints (GET /auth/me, liveness
    ping, etc.) should remain accessible to unverified users so they can
    still navigate the dashboard and verify their account.
    """
    cred_result = await db.exec(select(Credential).where(Credential.user_id == user.id))
    cred = cred_result.first()
    verified = bool(cred and cred.claims and cred.claims.get("email_verified", False))  # type: ignore[union-attr]
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified. Please verify your email to continue.",
        )
    return user
