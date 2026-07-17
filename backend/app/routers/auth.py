from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.session import get_session
from core.security import AuthResponse, LoginRequest
from app.service.auth import login_user as login, register_user as signUp
from app.models.user import UserCreate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
async def signup_user(req: UserCreate, db: AsyncSession = Depends(get_session)):
    """Endpoint to handle user signup."""
    return await signUp(req, db)


@router.post("/login", response_model=AuthResponse)
async def login_user(req: LoginRequest, db: AsyncSession = Depends(get_session)):
    """Endpoint to login a user"""
    return await login(req, db)