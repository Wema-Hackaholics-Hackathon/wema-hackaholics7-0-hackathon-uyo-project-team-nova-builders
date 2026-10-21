"""Consent schemas — request/response models for the consents API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class ConsentOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    platform: str
    scope: str
    status: str
    logo_url: str | None
    requested_at: datetime
    expires_at: datetime | None


class ConsentCreate(BaseModel):
    platform: str
    scope: str
    expires_at: datetime | None = None
    logo_url: str | None = None


class ConsentUpdate(BaseModel):
    status: Literal["approved", "revoked"]
