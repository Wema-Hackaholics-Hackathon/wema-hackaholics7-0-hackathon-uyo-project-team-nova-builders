from sqlalchemy.ext.asyncio import AsyncSession
from core.security import(
    AuthResponse, 
    create_access_token, 
    LoginRequest,
    authenticate_user,
    hash_password,
) 
from loguru import logger
from sqlmodel import select
from fastapi import HTTPException, status
from app.models.user import User, UserCreate



async def login_user(req: LoginRequest, db: AsyncSession) -> AuthResponse:
    """Function to login a user"""
    
    user = await authenticate_user(db, req)
    if not user:
        logger.warning(f"[LOG]: Invalid credentials for email: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    logger.success(f"User {user.email} logged in successfully.")
    token = create_access_token({"user_id": user.id})
    return AuthResponse(
        access_token=token,
        token_type="bearer"
    )


async def register_user(req: UserCreate, db: AsyncSession) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == req.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.warning(f"[LOG]: User with email {req.email} already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )
    
    new_user = User(
        firstname=req.firstname,
        lastname=req.lastname,
        email=req.email,
        password=hash_password(req.password),
        phone_number=req.phone_number,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)  

    logger.success(f"[LOG]: User {new_user.email} registered successfully.")
    token = create_access_token({"user_id": new_user.id})
    return AuthResponse(
        access_token=token,
        token_type="bearer"
    )
    
