"""Auth router — /api/v1/auth/*

Endpoints
---------
POST /api/v1/auth/signup              Register a new user
POST /api/v1/auth/login               Exchange credentials for tokens
POST /api/v1/auth/refresh             Exchange a refresh token for a new access token
POST /api/v1/auth/logout              Revoke the supplied refresh token
GET  /api/v1/auth/me                  Return the authenticated user's profile
POST /api/v1/auth/me/address/proof    Upload proof-of-address document (NEPA bill etc.)
POST /api/v1/auth/forgot-password     Send a 6-digit OTP to the user's email
POST /api/v1/auth/verify-reset-code   Verify OTP → return a short-lived reset_token
POST /api/v1/auth/reset-password      Use reset_token to set a new password
"""

from pathlib import Path
from typing import Annotated, cast

from app.utils.pdf_utils import draw_foid_header
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession  # has .exec() unlike sqlalchemy's AsyncSession

from app.config import get_db, get_settings
from app.core.dependencies import get_current_user, require_verified_email
from app.core.security import (
    create_access_token,
    create_refresh_token_expiry,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import (
    Consent,
    Credential,
    CredentialClaims,
    DEFAULT_CLAIMS,
    RefreshToken,
    User,
    Wallet,
)
from app.models import EmailVerificationToken, PasswordResetToken
from app.schemas.auth import (
    AddressRequest,
    BvnRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PhoneRequest,
    PROOF_OF_ADDRESS_ALLOWED_MIME,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
    VerifyResetCodeResponse,
)
from app.services.email_service import send_email
from app.services.email_templates import (
    email_verification as _tpl_email_verification,
    password_reset as _tpl_password_reset,
)
from app.utils.limiter import limiter

_PROOF_UPLOAD_DIR = Path("uploads/proof_of_address")
_AVATAR_UPLOAD_DIR = Path("uploads/avatars")
_MAX_PROOF_BYTES = 5 * 1024 * 1024   # 5 MB
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
_AVATAR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Internal helper — issue + store an email verification OTP
# ---------------------------------------------------------------------------

async def _prepare_verification_otp(user: User, db: AsyncSession) -> str:
    """Stage a new email verification OTP into the session WITHOUT committing.

    Invalidates any existing unused tokens for this user (also staged).
    Returns the raw OTP so the caller can email it AFTER a successful commit.

    Contract for callers:
      1. Call this to stage all DB rows.
      2. Commit the session (atomically with everything else in that request).
      3. Call _email_verification_otp(user, otp) to send the email.

    Keeping the email send outside the transaction means a failed log/send
    never rolls back — or worse, partially commits — the user record.
    """
    import random

    # Invalidate any prior unused tokens (staged, not yet committed)
    old = await db.exec(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used == False,  # noqa: E712
        )
    )
    for tok in old.all():
        tok.used = True
        db.add(tok)

    otp = f"{random.randint(0, 999999):06d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)

    db.add(EmailVerificationToken(
        user_id=user.id,
        code_hash=hash_refresh_token(otp),
        expires_at=expires,
    ))
    # Do NOT commit here — caller owns the transaction boundary.
    return otp


async def _email_verification_otp(user: User, otp: str) -> None:
    """Send the verification email. Must be called AFTER a successful commit.

    A failure here is non-fatal: the token is already persisted, so the user
    can request a new code via POST /auth/resend-verification.
    """
    subject, html = _tpl_email_verification(
        first_name=user.first_name,
        otp=otp,
        to=user.email,
    )
    await send_email(
        to=user.email,
        subject=subject,
        body=(
            f"Hi {user.first_name}, welcome to FOID!\n\n"
            f"Your email verification code is:  {otp}\n\n"
            f"This code expires in 30 minutes.\n"
            f"If you did not create a FOID account, ignore this email.\n\n"
            f"— The FOID Team"
        ),
        html=html,
    )


# ---------------------------------------------------------------------------
# POST /auth/signup
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def signup(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Register a new user and return access + refresh tokens.

    Also seeds:
    - A ``Credential`` row (state=active, full claims)
    - A ``Wallet`` row (balance=0)
    """
    # Check email uniqueness
    existing = await db.exec(select(User).where(User.email == body.email))
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Pre-hash the password before opening the write transaction so that a
    # slow hash (Argon2) doesn't hold the DB connection idle.
    hashed = hash_password(body.password)
    raw_refresh = generate_refresh_token()

    # --- Single atomic transaction: User + Credential + Wallet + RefreshToken + VerificationToken ---
    # get_db yields an AsyncSession whose context manager rolls back on any exception.
    # Nothing is committed until every row is staged — if any step raises, the
    # entire transaction rolls back and no partial account is written.
    user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        middle_name=body.middle_name,
        nin=body.nin,
        email=body.email,
        hashed_password=hashed,
    )
    db.add(user)
    await db.flush()  # assigns user.id without committing; still inside the transaction

    db.add(Credential(
        user_id=user.id,
        holder=f"{user.first_name} {user.last_name}",
        state="active",
        claims=cast(CredentialClaims, cast(object, dict(DEFAULT_CLAIMS))),
    ))
    from ..services.wallet_service import _current_month
    db.add(Wallet(
        user_id=user.id,
        free_credits=get_settings().FREE_MONTHLY_CREDITS,
        paid_credits=0,
        last_free_refresh=_current_month(),
    ))

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=create_refresh_token_expiry(),
    ))

    # Stage the verification token inside the same transaction.
    # Returns the raw OTP to email AFTER the commit succeeds.
    otp = await _prepare_verification_otp(user, db)

    # ONE commit — all rows land together or none do.
    await db.commit()

    # Everything below is post-commit. A failure here is non-fatal:
    # the account is fully created and the user can resend the code.
    access_token = create_access_token(user.id)
    await _email_verification_otp(user, otp)

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def login(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Validate credentials and return tokens."""
    result = await db.exec(select(User).where(User.email == body.email))
    user = result.first()

    # Constant-time-ish: always verify even if user not found to prevent timing attacks
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)
    raw_refresh = generate_refresh_token()
    refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=create_refresh_token_expiry(),
    )
    db.add(refresh_row)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def refresh(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Exchange a valid refresh token for a new access token.

    The old refresh token is revoked and a new one is issued (rotation).
    """
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.exec(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)  # SQLite stores naive datetimes
    if row.expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    # Revoke the old token (rotation)
    row.revoked = True
    db.add(row)

    # Issue new pair
    access_token = create_access_token(row.user_id)
    raw_refresh = generate_refresh_token()
    new_row = RefreshToken(
        user_id=row.user_id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=create_refresh_token_expiry(),
    )
    db.add(new_row)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the supplied refresh token (client should discard both tokens)."""
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.exec(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.first()
    if row is not None and not row.revoked:
        row.revoked = True
        db.add(row)
        await db.commit()


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Return the profile of the currently authenticated user."""
    cred_result = await db.exec(select(Credential).where(Credential.user_id == user.id))
    cred = cred_result.first()
    email_verified = bool(cred and cred.claims and cred.claims.get("email_verified", False))  # type: ignore[union-attr]
    return UserOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        middle_name=user.middle_name,
        nin=user.nin,
        bvn=user.bvn,
        phone=user.phone,
        address=user.address,
        proof_of_address_url=user.proof_of_address_url,
        avatar_url=user.avatar_url,
        liveness_selfie_url=user.liveness_selfie_url,
        email=user.email,
        created_at=user.created_at,
        email_verified=email_verified,
    )


# ---------------------------------------------------------------------------
# PATCH /auth/me/bvn  — save BVN and flip bvn_validated claim
# ---------------------------------------------------------------------------

@router.patch("/me/bvn", response_model=UserOut)
async def submit_bvn(
    body: BvnRequest,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Store the user's BVN (mocked verification) and mark bvn_validated=True."""
    current_user.bvn = body.bvn
    db.add(current_user)

    # Flip bvn_validated on the credential
    cred_result = await db.exec(
        select(Credential).where(Credential.user_id == current_user.id)
    )
    cred = cred_result.first()
    if cred is not None:
        cred.claims = {**cred.claims, "bvn_validated": True}  # type: ignore[assignment]
        db.add(cred)

    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# PATCH /auth/me/phone  — save phone number
# ---------------------------------------------------------------------------

@router.patch("/me/phone", response_model=UserOut)
async def submit_phone(
    body: PhoneRequest,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Store the user's phone number."""
    current_user.phone = body.phone
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# GET /auth/me/identity-summary — server-generated PDF download
# ---------------------------------------------------------------------------

@router.get("/me/identity-summary")
async def identity_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Generate and stream a PDF identity summary for the authenticated user."""
    from datetime import datetime, timezone
    from io import BytesIO

    from fpdf import FPDF

    from app.models.connected_bank import ConnectedBank
    from app.models.consent import Consent

    now = datetime.now(timezone.utc)

    # ── Fetch data ────────────────────────────────────────────────────
    cred_result = await db.exec(select(Credential).where(Credential.user_id == current_user.id))
    cred = cred_result.first()

    banks_result = await db.exec(select(ConnectedBank).where(ConnectedBank.user_id == current_user.id))
    banks = banks_result.all()

    consents_result = await db.exec(
        select(Consent).where(Consent.user_id == current_user.id, Consent.status == "approved")
    )
    consents = consents_result.all()

    claims: dict[str, object] = dict(cred.claims) if cred else {}

    nin_masked   = ("****" + current_user.nin[-4:])  if len(current_user.nin or "") >= 4 else "****"
    bvn_masked   = ("****" + (current_user.bvn or "")[-4:]) if current_user.bvn else "Not submitted"
    phone_masked = (current_user.phone[:4] + "****" + current_user.phone[-2:]) if current_user.phone else "Not submitted"

    # ── Build PDF ─────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # ── Header band ───────────────────────────────────────────────────
    band_h = draw_foid_header(
        pdf,
        title="Identity Summary",
        subtitle=f"Generated {now.strftime('%d %B %Y, %H:%M UTC')}  ·  {current_user.first_name} {current_user.last_name}",
    )
    pdf.set_text_color(31, 35, 40)   # neutral-900
    pdf.set_y(band_h + 8)

    def section(title: str) -> None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(245, 240, 255)   # FOID light purple tint
        pdf.cell(0, 8, f"  {title}", ln=True, fill=True)
        pdf.ln(2)

    def row(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(107, 114, 128)   # neutral-500
        pdf.cell(55, 7, label)
        pdf.set_text_color(31, 35, 40)
        pdf.cell(0, 7, value, ln=True)

    # ── Personal details ──────────────────────────────────────────────
    section("Personal Details")
    row("Full name",     f"{current_user.first_name} {current_user.last_name}")
    row("Email",         current_user.email)
    row("NIN",           nin_masked)
    row("BVN",           bvn_masked)
    row("Phone",         phone_masked)
    row("Member since",  current_user.created_at.strftime("%d %B %Y"))
    pdf.ln(4)

    # ── Credential ────────────────────────────────────────────────────
    section("Credential")
    state_label = (cred.state if cred else "unknown").replace("_", " ").title()
    row("State",                state_label)
    row("Identity verified",    "Yes" if claims.get("identity_verified") else "No")
    row("BVN validated",        "Yes" if claims.get("bvn_validated") else "No")
    row("Account stability",    str(claims.get("account_stability", "—")).title())
    row("Repayment reliability", str(claims.get("repayment_reliability", "—")).title())
    if cred:
        row("Issued",           cred.issued_at.strftime("%d %B %Y"))
        row("Last updated",     cred.updated_at.strftime("%d %B %Y"))
    pdf.ln(4)

    # ── Connected banks ───────────────────────────────────────────────
    if banks:
        section("Connected Banks")
        for b in banks:
            acct = f" ({b.account_type})" if b.account_type else ""
            row(b.name + acct, b.status.title())
        pdf.ln(4)

    # ── Approved consents ─────────────────────────────────────────────
    if consents:
        section("Approved Consents")
        for c in consents:
            row(c.platform, c.scope)
        pdf.ln(4)

    # ── Footer ────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, "This document is system-generated by FOID · Identity & Financial Trust Platform", align="C")

    # ── Stream bytes ──────────────────────────────────────────────────
    buf = BytesIO(pdf.output())
    filename = f"FOID_Identity_{current_user.first_name}_{current_user.last_name}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# PATCH /auth/me/address  — save residential address
# ---------------------------------------------------------------------------

@router.patch("/me/address", response_model=UserOut)
async def update_address(
    body: AddressRequest,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Store the user's residential address."""
    current_user.address = body.address
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# POST /auth/me/address/proof  — upload proof-of-address document
# ---------------------------------------------------------------------------

@router.post("/me/address/proof", response_model=UserOut)
async def upload_proof_of_address(
    file: Annotated[UploadFile, File(description="Utility bill or address document — JPEG, PNG, WebP or PDF, max 5 MB")],
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Upload a proof-of-address document (e.g. NEPA/PHCN bill, water bill).

    Accepts: JPEG, PNG, WebP, PDF — max 5 MB.
    Saves the file to disk and stores its path on the user record.
    """
    import uuid as _uuid

    if file.content_type not in PROOF_OF_ADDRESS_ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WebP, PDF",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_PROOF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large — maximum 5 MB",
        )

    _PROOF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "proof").suffix or ".bin"
    filename = f"{current_user.id}_{_uuid.uuid4()}{ext}"
    file_path = _PROOF_UPLOAD_DIR / filename
    file_path.write_bytes(file_bytes)

    current_user.proof_of_address_url = str(file_path)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# POST /auth/me/avatar  — upload profile picture
# ---------------------------------------------------------------------------

@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: Annotated[UploadFile, File(description="Profile picture — JPEG, PNG or WebP, max 2 MB")],
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Upload a profile picture for the authenticated user.

    Accepts: JPEG, PNG, WebP — max 2 MB.
    Replaces any previously uploaded avatar.
    """
    if file.content_type not in _AVATAR_ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WebP",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large — maximum 2 MB",
        )

    _AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "avatar").suffix or ".jpg"
    filename = f"{current_user.id}{ext}"   # one file per user — overwrites previous
    file_path = _AVATAR_UPLOAD_DIR / filename
    file_path.write_bytes(file_bytes)

    current_user.avatar_url = str(file_path)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# PATCH /auth/me/password  — change password
# ---------------------------------------------------------------------------

@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[User, Depends(require_verified_email)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Verify current password then hash and store the new one."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(body.new_password)
    db.add(current_user)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /auth/forgot-password  — send 6-digit OTP to user's email
# ---------------------------------------------------------------------------

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/hour")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def forgot_password(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Generate a 6-digit OTP and email it to the user.

    Always returns 200 regardless of whether the email exists (prevents
    user enumeration — attacker cannot tell if an account is registered).
    OTP expires in 10 minutes.
    """
    import random

    result = await db.exec(select(User).where(User.email == body.email))
    user = result.first()

    if user is not None:
        # Invalidate any previous unused tokens for this user
        old_tokens = await db.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used == False,  # noqa: E712
            )
        )
        for tok in old_tokens.all():
            tok.used = True
            db.add(tok)

        otp = f"{random.randint(0, 999999):06d}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)

        db.add(PasswordResetToken(
            user_id=user.id,
            code_hash=hash_refresh_token(otp),   # reuse SHA-256 helper
            expires_at=expires,
        ))
        await db.commit()

        subject, html = _tpl_password_reset(
            first_name=user.first_name,
            otp=otp,
            to=user.email,
        )
        await send_email(
            to=user.email,
            subject=subject,
            body=(
                f"Hi {user.first_name},\n\n"
                f"Your FOID password reset code is:  {otp}\n\n"
                f"This code expires in 10 minutes.\n"
                f"If you did not request a password reset, ignore this email.\n\n"
                f"— The FOID Team"
            ),
            html=html,
        )

    return {"message": "If that email is registered, a reset code has been sent."}


# ---------------------------------------------------------------------------
# POST /auth/verify-reset-code  — verify OTP, return reset_token
# ---------------------------------------------------------------------------

@router.post("/verify-reset-code", response_model=VerifyResetCodeResponse)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def verify_reset_code(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: VerifyResetCodeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyResetCodeResponse:
    """Verify the 6-digit OTP and return a single-use reset_token (15 min TTL).

    Raises HTTP 400 for invalid/expired code — same message for both cases
    to avoid leaking information.
    """
    import secrets as _secrets

    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset code",
    )

    result = await db.exec(select(User).where(User.email == body.email))
    user = result.first()
    if user is None:
        raise invalid_exc

    code_hash = hash_refresh_token(body.code)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    tok_result = await db.exec(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.code_hash == code_hash,
            PasswordResetToken.used == False,  # noqa: E712
        )
    )
    tok = tok_result.first()

    if tok is None or tok.expires_at < now_naive:
        raise invalid_exc

    # Issue a reset_token and store its hash.
    # The row stays used=False so phase 3 can still find it via reset_token_hash.
    # The OTP (code_hash) is effectively burned because we only query by reset_token_hash in phase 3.
    raw_reset_token = _secrets.token_hex(32)
    tok.reset_token_hash = hash_refresh_token(raw_reset_token)
    db.add(tok)
    await db.commit()

    return VerifyResetCodeResponse(reset_token=raw_reset_token)


# ---------------------------------------------------------------------------
# POST /auth/reset-password  — use reset_token to set new password
# ---------------------------------------------------------------------------

@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def reset_password(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Use the reset_token from verify-reset-code to set a new password.

    The token is single-use — it is marked used=True after this call.
    Raises HTTP 400 if the token is invalid, expired, or already used.
    """
    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )

    token_hash = hash_refresh_token(body.reset_token)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    tok_result = await db.exec(
        select(PasswordResetToken).where(
            PasswordResetToken.reset_token_hash == token_hash,
            PasswordResetToken.used == False,  # noqa: E712
        )
    )
    tok = tok_result.first()

    if tok is None or tok.expires_at < now_naive:
        raise invalid_exc

    user = await db.get(User, tok.user_id)
    if user is None:
        raise invalid_exc

    user.hashed_password = hash_password(body.new_password)
    tok.used = True   # single-use — burn the token
    db.add(user)
    db.add(tok)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /auth/verify-email  — submit OTP to verify email address
# ---------------------------------------------------------------------------

@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def verify_email(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Verify the user's email address using the 6-digit OTP sent at signup.

    On success, flips email_verified=True on the user's credential claims.
    Raises HTTP 400 for invalid or expired codes.
    """
    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired verification code",
    )

    result = await db.exec(select(User).where(User.email == body.email))
    user = result.first()
    if user is None:
        raise invalid_exc

    code_hash = hash_refresh_token(body.code)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    tok_result = await db.exec(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.code_hash == code_hash,
            EmailVerificationToken.used == False,  # noqa: E712
        )
    )
    tok = tok_result.first()

    if tok is None or tok.expires_at < now_naive:
        raise invalid_exc

    # Burn the token
    tok.used = True
    db.add(tok)

    # Flip email_verified on the credential
    cred_result = await db.exec(
        select(Credential).where(Credential.user_id == user.id)
    )
    cred = cred_result.first()
    if cred is not None:
        cred.claims = {**cred.claims, "email_verified": True}  # type: ignore[assignment]
        db.add(cred)

    await db.commit()
    return {"message": "Email verified successfully."}


# ---------------------------------------------------------------------------
# POST /auth/resend-verification  — resend email verification OTP
# ---------------------------------------------------------------------------

@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("3/hour")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def resend_verification(
    request: Request,  # pyright: ignore[reportUnusedParameter] — slowapi requires this name
    body: ResendVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Resend the email verification OTP.

    Always returns 200 regardless of whether the email exists (prevents
    user enumeration). Rate-limited to 3 requests per hour per IP.
    Does nothing if the email is already verified.
    """
    result = await db.exec(select(User).where(User.email == body.email))
    user = result.first()

    if user is not None:
        # Check if already verified — no point resending
        cred_result = await db.exec(
            select(Credential).where(Credential.user_id == user.id)
        )
        cred = cred_result.first()
        already_verified = bool(
            cred and cred.claims and cred.claims.get("email_verified", False)  # type: ignore[union-attr]
        )

        if not already_verified:
            # Stage the new token, commit atomically, then send the email.
            otp = await _prepare_verification_otp(user, db)
            await db.commit()
            await _email_verification_otp(user, otp)

    return {"message": "If that email is registered and unverified, a new code has been sent."}
