# app/dependencies/kyc_guards.py
from fastapi import Depends, HTTPException, status
from sqlmodel import select
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from core.session import get_session
from core.security import get_current_user
from app.models.user import User
from app.models.kyc import KYC, KYCStatus
from loguru import logger


async def docs_required(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> KYC:
    """
    Dependency Guard:
    Fetches the user's KYC record and verifies they have passed document checks.
    If valid, returns the KYC record directly to the route handler.
    If invalid or missing, immediately short-circuits the request with a 400/403.
    """
    log_session = logger.bind(user_id=current_user.id)
    log_session.debug("[DEBUG]: checking if documents a loaded......")
    statement = await db.execute(select(KYC).where(KYC.user_id == current_user.id))
    kyc_record = statement.scalar_one_or_none()

    # 1. No KYC record started at all
    if not kyc_record:
        log_session.error("[ERROR]: KYC error, submit BVN/NIN first.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No document verification found. Please submit BVN/NIN first."
        )

    # 2. Check status (Must be DOCUMENTS_VERIFIED or pending liveness)
    if kyc_record.verification_status == KYCStatus.PENDING:
        log_session.error("[ERROR]: KYC verification still pending or failed.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document verification pending or failed. Cannot proceed to liveness check."
        )

    # Return the verified record so the liveness handler can use it directly
    return kyc_record


# Custom Type Alias for ultra-clean route signatures
VerifiedDocsKYC = Annotated[KYC, Depends(docs_required)]