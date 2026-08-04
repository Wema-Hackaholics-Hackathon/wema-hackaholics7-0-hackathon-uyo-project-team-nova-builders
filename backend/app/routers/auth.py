from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.session import get_session
from core.security import AuthResponse, LoginRequest
from app.service.auth import login_user as login, register_user as signUp
from app.models.user import UserCreate
from core.limiter import limiter

router = APIRouter(
    prefix="/auth", 
    tags=["auth"]
)


@router.post("/signup", response_model=AuthResponse)
@limiter.limit("4/minute")
async def signup_user(
    request: Request, 
    payload: UserCreate, 
    db: AsyncSession = Depends(get_session)
):
    """Endpoint to handle user signup."""
    return await signUp(payload, db)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("7/minute")
async def login_user(
    request: Request, 
    payload: LoginRequest, 
    db: AsyncSession = Depends(get_session)
):
    """Endpoint to login a user"""
    return await login(payload, db)

@router.post("/google-login", response_model=AuthResponse)
async def login_with_google():
    """Endpoint for signing-up/logging-in with social provider"""
    ...
    