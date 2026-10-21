"""Credential & trigger request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class CredentialClaimsOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    identity_verified: bool
    bvn_validated: bool
    # Admin-verified flags
    nin_verified: bool
    phone_verified: bool
    bill_verified: bool
    email_verified: bool
    age_over_18: bool
    income_band: Literal["low", "mid", "high"]
    account_stability: Literal["stable", "variable", "poor"]
    repayment_reliability: Literal["reliable", "variable", "poor"]


class CredentialOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    holder: str
    state: str
    claims: CredentialClaimsOut
    issued_at: datetime
    updated_at: datetime


class TriggerRequest(BaseModel):
    event: Literal[
        "missed_repayment",
        "suspicious_activity",
        "income_drop",
        "manual_revoke",
        "review_cleared",
        "appeal_approved",
        "repayment_restored",
    ]


class TriggerResponse(BaseModel):
    credential: CredentialOut
    notification: "NotificationOut"


from .notification import NotificationOut  # noqa: E402  (avoid circular at top)

_ = TriggerResponse.model_rebuild()
