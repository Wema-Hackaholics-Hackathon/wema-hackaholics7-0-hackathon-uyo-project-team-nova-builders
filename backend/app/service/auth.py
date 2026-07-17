from sqlalchemy.ext.asyncio import AsyncSession
from core.security import AuthResponse, create_access_token, LoginRequest
from loguru import logger
from sqlmodel import select
from fastapi import HTTPException, status
from app.models.user import User, UserCreate



async def login_user(req: LoginRequest, db: AsyncSession) -> AuthResponse:
    """Function to login a user"""

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or user.password != req.password:
        logger.error(f"Invalid credentials for email: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    logger.info(f"User {user.email} logged in successfully.")
    token = create_access_token({"user_id": user.id})
    return AuthResponse(
        access_token=token,
        token_type="bearer"
    )


async def register_user(req: UserCreate, db: AsyncSession) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == req.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.error(f"User with email {req.email} already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )
    
    new_user = User(
        firstname=req.firstname,
        lastname=req.lastname,
        email=req.email,
        password=req.password,
        phone_number=req.phone_number,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)  

    logger.info(f"User {new_user.email} registered successfully.")
    token = create_access_token({"user_id": new_user.id})
    return AuthResponse(
        access_token=token,
        token_type="bearer"
    )
    
