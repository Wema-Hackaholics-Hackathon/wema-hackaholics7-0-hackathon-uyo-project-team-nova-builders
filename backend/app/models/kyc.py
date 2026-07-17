from sqlmodel import SQLModel, Field, Relationship
from utils import customKYCID
from pydantic import EmailStr, SecretStr
from datetime import datetime, UTC
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User  

class KYCStatus(StrEnum):
    """Enum for KYC verification status"""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class KYC(SQLModel, table=True):
    """Model for KYC db"""
    
    id: str = Field(default_factory=customKYCID, primary_key=True, index=True)
    user_id: str = Field(..., foreign_key="user.id", unique=True)
    bvn: str = Field(...)
    nin: str = Field(...)
    verification_status: KYCStatus = Field(default=KYCStatus.PENDING)
    created_at: str = datetime.now(UTC).isoformat()

    user: "User" = Relationship(back_populates="kyc")

    @property
    def user_fn(self) -> str:
        return self.user.firstname if self.user else ""

    @property
    def user_ln(self) -> str:
        return self.user.lastname if self.user else ""

    @property
    def user_email(self) -> str:
        return self.user.email if self.user else ""

    @property
    def phone(self) -> str:
        return self.user.phone_number if self.user else ""