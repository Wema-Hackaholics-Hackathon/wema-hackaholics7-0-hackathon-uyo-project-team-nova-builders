# app/routes/kyc.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.session import get_session
from core.security import get_current_user
from core.deps.guards import VerifiedDocsKYC
from app.models.user import User
from app.models.kyc import KYCResponse, VerifyKYCRequest

router = APIRouter(prefix="/kyc", tags=["KYC Stage"])


@router.post("/verify-documents", response_model=KYCResponse)
async def verify_documents(
    req: VerifyKYCRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Stage 3a: Step 1 - Document check (NIN & BVN)"""
    ...


@router.post("/verify-liveness", response_model=KYCResponse)
async def verify_liveness(
    kyc_record: VerifiedDocsKYC,
    session: AsyncSession = Depends(get_session)
):
    """
    Stage 3b: Step 2 - Liveness Selfie Check
    This endpoint CANNOT be reached unless `require_verified_docs` passes!
    """
    ...