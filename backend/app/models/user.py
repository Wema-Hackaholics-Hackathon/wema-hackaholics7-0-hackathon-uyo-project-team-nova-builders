from sqlmodel import SQLModel, Field, Relationship
from utils import customID
from pydantic import EmailStr, SecretStr
from datetime import datetime, UTC
from typing import TYPE_CHECKING
from app.models.kyc import KYC

if TYPE_CHECKING:
    from app.models.kyc import KYC


class User(SQLModel, table=True):
    """Model for User db"""
    
    id: str = Field(default_factory=customID, primary_key=True, index=True, unique=True)
    firstname: str = Field(...)
    lastname: str = Field(...)
    email: EmailStr = Field(...)
    password: str = Field(...)
    phone_number: str = Field(...)
    created_at: str = datetime.now(UTC).isoformat()

    kyc: "KYC" = Relationship(back_populates="user")


class UserCreate(SQLModel):
    """Schema for creating a user"""
    
    firstname: str = Field(...)
    lastname: str = Field(...)
    email: EmailStr = Field(...)
    password: str = Field(...)
    phone_number: str = Field(...)


class UserResponse(SQLModel):
    """Schema for returning a user"""

    id: str
    firstname: str
    lastname: str
    email: EmailStr
    phone_number: str