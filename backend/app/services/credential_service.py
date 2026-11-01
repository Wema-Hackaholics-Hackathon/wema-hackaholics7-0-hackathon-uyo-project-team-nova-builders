"""Credential service — ports the TRIGGER_EVENTS state machine from
frontend/src/contexts/CredentialContext.tsx to the backend.

apply_trigger():
  1. Looks up the event in TRIGGER_EVENTS
  2. Validates the requiredState guard → raises HTTP 409 on mismatch
  3. Computes new state + updated claims (exactly mirrors frontend logic)
  4. Persists the Credential update
  5. Inserts an immutable Notification row
  6. Returns (updated_credential, new_notification)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models.credential import Credential, CredentialClaims
from ..models.notification import Notification


# ---------------------------------------------------------------------------
# Trigger event table — exact port of TRIGGER_EVENTS in CredentialContext.tsx
# ---------------------------------------------------------------------------

TriggerEventName = Literal[
    "missed_repayment",
    "suspicious_activity",
    "income_drop",
    "manual_revoke",
    "review_cleared",
    "appeal_approved",
    "repayment_restored",
]

CredentialStateName = Literal["active", "under_review", "downgraded", "revoked"]


@dataclass(frozen=True)
class TriggerEventMeta:
    event: TriggerEventName
    required_state: CredentialStateName | None  # None = any state allowed
    result_state: CredentialStateName
    message: str                                # title shown in notification
    reason: str
    action: str


_STATE_CHANGE_LABEL: dict[str, str] = {
    "active": "Credential restored to Active",
    "under_review": "Credential placed Under Review",
    "downgraded": "Credential Downgraded",
    "revoked": "Credential Revoked",
}

TRIGGER_EVENTS: list[TriggerEventMeta] = [
    TriggerEventMeta(
        event="missed_repayment",
        required_state="active",
        result_state="under_review",
        message=_STATE_CHANGE_LABEL["under_review"],
        reason="A missed repayment was detected on your connected bank account.",
        action="Review your linked accounts and resolve any outstanding payments.",
    ),
    TriggerEventMeta(
        event="suspicious_activity",
        required_state="active",
        result_state="under_review",
        message=_STATE_CHANGE_LABEL["under_review"],
        reason="Unusual transaction patterns were detected on your account.",
        action="Verify your recent transactions and contact support if needed.",
    ),
    TriggerEventMeta(
        event="income_drop",
        required_state="under_review",
        result_state="downgraded",
        message=_STATE_CHANGE_LABEL["downgraded"],
        reason="A significant income drop (>40%) was detected over two consecutive months.",
        action="Upload recent proof of income or link an additional account.",
    ),
    TriggerEventMeta(
        event="review_cleared",
        required_state="under_review",
        result_state="active",
        message=_STATE_CHANGE_LABEL["active"],
        reason="Your account review has been completed with no outstanding issues.",
        action="No action required — your credential is fully active again.",
    ),
    TriggerEventMeta(
        event="repayment_restored",
        required_state="downgraded",
        result_state="under_review",
        message=_STATE_CHANGE_LABEL["under_review"],
        reason="Repayment activity has resumed. Your credential is back under review.",
        action="Continue maintaining regular repayments to restore full status.",
    ),
    TriggerEventMeta(
        event="appeal_approved",
        required_state="downgraded",
        result_state="active",
        message=_STATE_CHANGE_LABEL["active"],
        reason="Your appeal has been reviewed and approved.",
        action="No action required — your credential is fully active again.",
    ),
    TriggerEventMeta(
        event="manual_revoke",
        required_state=None,               # any state
        result_state="revoked",
        message=_STATE_CHANGE_LABEL["revoked"],
        reason="Your FOID credential has been manually revoked.",
        action="Contact support or re-verify your identity to issue a new credential.",
    ),
]

_EVENT_MAP: dict[TriggerEventName, TriggerEventMeta] = {e.event: e for e in TRIGGER_EVENTS}


# ---------------------------------------------------------------------------
# Claims mutation — exact port of the claims-update block in CredentialContext
# ---------------------------------------------------------------------------

def _updated_claims(prev: CredentialClaims, result_state: str) -> CredentialClaims:
    return {
        **prev,
        "account_stability": (
            "stable" if result_state == "active"
            else "variable" if result_state == "under_review"
            else "poor"
        ),
        "repayment_reliability": (
            "reliable" if result_state == "active"
            else "variable" if result_state == "under_review"
            else "poor"
        ),
        "income_band": (
            "low" if result_state == "downgraded"
            else "high" if result_state == "active"
            else prev["income_band"]
        ),
    }  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------

async def apply_trigger(
    *,
    credential: Credential,
    event: TriggerEventName,
    db: AsyncSession,
) -> tuple[Credential, Notification]:
    """Apply a trigger event to an existing credential.

    Raises HTTP 409 if the credential's current state does not satisfy the
    event's requiredState guard (mirrors the frontend guard in CredentialContext).

    Returns the updated Credential and the newly created Notification.
    Both are already added to the session; the caller must commit.
    """
    meta = _EVENT_MAP.get(event)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown event")

    # Guard: requiredState check
    if meta.required_state is not None and credential.state != meta.required_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Event '{event}' requires credential state '{meta.required_state}', "
                f"but current state is '{credential.state}'."
            ),
        )

    prev_state = credential.state

    # Mutate credential
    credential.state = meta.result_state
    credential.claims = _updated_claims(
        credential.claims,  # type: ignore[arg-type]
        meta.result_state,
    )
    credential.updated_at = datetime.now(timezone.utc)

    # Create notification
    notification = Notification(
        id=str(uuid.uuid4()),
        user_id=credential.user_id,
        message=meta.message,
        change=f"{prev_state} → {meta.result_state}",
        reason=meta.reason,
        action=meta.action,
    )

    db.add(credential)
    db.add(notification)

    return credential, notification
