from core.config import settings
from sqlmodel import SQLModel
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import User
from core.config import settings
from core.session import get_session
from typing import Annotated, Optional
from datetime import datetime, timedelta, timezone

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class AuthResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(SQLModel):
    email: EmailStr
    password: str


auth_scheme = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Function to create access token"""

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire, "user_id": data.get("user_id")})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Function to decode access token"""
    data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return data


async def get_user_by_Id(session: AsyncSession, id: str) -> User | None:
    """Retrieve a user's id from the database."""

    result = await session.execute(select(User).where(User.id == id))
    return result.scalar_one_or_none()



async def get_current_user(
    token: Annotated[HTTPAuthorizationCredentials, Depends(auth_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Function to get the current user logged in"""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

    except Exception:
        raise credentials_exception

    user = await get_user_by_Id(session, id=user_id)
    if user is None:
        raise credentials_exception
    return user