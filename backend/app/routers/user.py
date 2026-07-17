from fastapi import APIRouter, Depends
from typing import Annotated
from core.security import get_current_user
from app.models.user import User, UserResponse


router = APIRouter(
    prefix='/user',
    tags=['user'],
)


@router.get('/me', response_model=UserResponse)
async def get_my_user(user: Annotated[User, Depends(get_current_user)]):
    """Endpoint to fetch the current user logged in"""
    return user