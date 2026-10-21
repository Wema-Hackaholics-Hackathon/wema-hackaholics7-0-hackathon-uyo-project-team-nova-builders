"""Auth request / response Pydantic schemas.

Password validation rules mirror SignupPage.tsx PWD_RULES exactly:
  - At least 8 characters
  - One uppercase letter (A–Z)
  - One lowercase letter (a–z)
  - One number (0–9)
  - One special character (anything not alphanumeric)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    middle_name: str | None = None
    nin: str
    email: EmailStr
    password: str

    @field_validator("first_name", "last_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be blank")
        return v.strip()

    @field_validator("nin")
    @classmethod
    def must_be_11_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{11}", v.strip()):
            raise ValueError("NIN must be exactly 11 digits")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("one number")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"password must contain: {', '.join(errors)}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    middle_name: str | None
    nin: str
    bvn: str | None
    phone: str | None
    address: str | None
    proof_of_address_url: str | None
    avatar_url: str | None
    liveness_selfie_url: str | None
    email: str
    created_at: datetime


class BvnRequest(BaseModel):
    bvn: str

    @field_validator("bvn")
    @classmethod
    def must_be_11_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{11}", v.strip()):
            raise ValueError("BVN must be exactly 11 digits")
        return v.strip()


class AddressRequest(BaseModel):
    address: str

    @field_validator("address")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("address cannot be blank")
        return v.strip()


# Allowed MIME types for proof-of-address uploads
PROOF_OF_ADDRESS_ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("one number")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"password must contain: {', '.join(errors)}")
        return v


class PhoneRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def must_be_valid(cls, v: str) -> str:
        # Accept +234XXXXXXXXXX or 0XXXXXXXXXX (10–14 digits after optional +)
        cleaned = re.sub(r"\s+", "", v.strip())
        if not re.fullmatch(r"(\+?\d{10,14})", cleaned):
            raise ValueError("Phone must be 10–14 digits, optionally prefixed with +")
        return cleaned

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("code")
    @classmethod
    def must_be_6_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v.strip()):
            raise ValueError("code must be exactly 6 digits")
        return v.strip()


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("code")
    @classmethod
    def must_be_6_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v.strip()):
            raise ValueError("code must be exactly 6 digits")
        return v.strip()


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("one number")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"password must contain: {', '.join(errors)}")
        return v


class VerifyResetCodeResponse(BaseModel):
    reset_token: str

