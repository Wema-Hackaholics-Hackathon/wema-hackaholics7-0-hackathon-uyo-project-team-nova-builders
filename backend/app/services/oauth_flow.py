"""'Continue with FOID' — the OAuth 2.0 authorization-code flow with PKCE.

  business page ──(client id, state, nonce, PKCE challenge)──▶ FOID popup  /oauth/authorize
  popup: sign in (email code or FOID session) → consent → only-missing steps → face re-match (live,
         new business) → approve → one-time code back to the business page (postMessage or redirect)
  business server ──(code + PKCE verifier + client secret / signed key)──▶ /api/open/v1/oauth/token
         → the person's result (subject + attestations)

People with no FOID account do the existing hosted verification inside the popup, then may tap
"Save to FOID". Test apps: real sign-in and the real name; every other field is sandbox data.
See docs/continue-with-foid.md.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from jose import JWTError, jwt
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.api_errors import ApiError
from app.core.crypto import encrypt_str, new_token, sha256_hex
from app.core.security import create_ticket, hash_password
from app.models import (
    CheckResult,
    ConsentGrant,
    Credential,
    DEFAULT_CLAIMS,
    FaceEnrolment,
    LivenessAttempt,
    OAuthApp,
    OAuthClientSecret,
    OAuthRequest,
    Organisation,
    Subject,
    SubjectFace,
    User,
    Verification,
    Wallet,
)
from app.services import checks_service as cs
from app.services import consent_service as consent
from app.services import face_match_service as fm
from app.services import oauth_apps as oa
from app.services.email_service import send_email
from app.services.email_templates import oauth_code

REQUEST_TTL = timedelta(minutes=15)
CODE_TTL = timedelta(seconds=60)
OTP_TTL = timedelta(minutes=10)
MAX_OTP_ATTEMPTS = 5
MAX_OTP_SENDS = 5
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
_PKCE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")          # S256 challenge (base64url, no padding)
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")     # RFC 7636 code_verifier

# Test apps: the real name, everything else from here.
SANDBOX = {
    "date_of_birth": "1990-01-01", "nin_last4": "0001", "bvn_last4": "0002",
    "email": "sandbox.person@example.com", "phone": "+2348000000001",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OAuthError(Exception):
    """Token-endpoint errors in OAuth's own format: {"error", "error_description"}."""

    def __init__(self, error: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.error, self.description, self.status = error, description, status


# ── starting a request (the popup opens) ────────────────────────────────────

async def start(db: AsyncSession, *, client_id: str, response_mode: str, origin: str | None, redirect_uri: str | None,
                scope: str, state: str, nonce: str | None, code_challenge: str, code_challenge_method: str) -> OAuthRequest:
    """Validate everything about the business's request. Errors are shown in the popup — never redirected."""
    app = (await db.exec(select(OAuthApp).where(OAuthApp.client_id == client_id))).first()
    if app is None or app.disabled_at is not None:
        raise ApiError(400, "invalid_client", "This app isn't registered with FOID (unknown client_id)")
    org = await db.get(Organisation, app.org_id)
    if org is None or org.status != "active":
        raise ApiError(400, "invalid_client", "This business can't use FOID sign-in right now")
    if app.env == "live" and not org.live_enabled:
        raise ApiError(400, "invalid_client", "This business hasn't finished FOID verification yet")
    if response_mode == "web_message":
        if not origin or not (origin in app.origins or (app.env == "test" and oa.is_loopback(origin))):
            raise ApiError(400, "invalid_origin", f"{origin or 'This website'} isn't an allowed origin for this app")
        redirect_uri = None
    elif response_mode == "query":
        if not redirect_uri or not (redirect_uri in app.redirect_uris or (app.env == "test" and oa.is_loopback(redirect_uri))):
            raise ApiError(400, "invalid_redirect_uri", "That redirect URI isn't registered for this app")
        origin = None
    else:
        raise ApiError(400, "invalid_request", "response_mode must be web_message or query")
    if code_challenge_method != "S256" or not _PKCE.match(code_challenge or ""):
        raise ApiError(400, "invalid_request", "PKCE is required: code_challenge (S256) missing or malformed")
    if not (8 <= len(state or "") <= 512):
        raise ApiError(400, "invalid_request", "state is required (8–512 characters)")
    if nonce is not None and len(nonce) > 512:
        raise ApiError(400, "invalid_request", "nonce is too long")
    asked = {s for s in re.split(r"[\s,]+", scope or "") if s} | {"profile"}
    extra = asked - set(app.scopes)
    if extra:
        raise ApiError(400, "invalid_scope", f"This app isn't allowed to ask for: {', '.join(sorted(extra))}")
    req = OAuthRequest(app_id=app.id, org_id=app.org_id, env=app.env, response_mode=response_mode, origin=origin,
                       redirect_uri=redirect_uri, scopes=sorted(asked), state=state, nonce=nonce,
                       code_challenge=code_challenge, expires_at=_now() + REQUEST_TTL)
    db.add(req)
    await db.flush()
    return req


async def load(db: AsyncSession, request_id: str, *, open_only: bool = True) -> tuple[OAuthRequest, OAuthApp]:
    req = await db.get(OAuthRequest, request_id)
    if req is None:
        raise ApiError(404, "request_not_found", "This sign-in link isn't valid — start again from the app")
    app = await db.get(OAuthApp, req.app_id)
    assert app is not None
    if open_only:
        if req.status != "pending":
            raise ApiError(409, "request_closed", "This sign-in has already finished — start again from the app")
        if cs.as_utc(req.expires_at) < _now() or app.disabled_at is not None:   # type: ignore[operator]
            raise ApiError(410, "request_expired", "This sign-in took too long — start again from the app")
    return req, app


async def view(db: AsyncSession, req: OAuthRequest, app: OAuthApp) -> dict[str, Any]:
    org = await db.get(Organisation, app.org_id)
    assert org is not None
    return {
        "id": req.id,
        "status": req.status,
        "test_mode": req.env == "test",
        "app": {"name": app.name, "client_id": app.client_id},
        "business": {**await cs.org_branding(db, app.org_id), "kyb_approved": org.kyb_status == "approved"},
        "scopes": [{"scope": s, "description": consent.SCOPES[s]} for s in req.scopes],
        "email": req.email,
        "expires_at": cs.iso(req.expires_at),
    }


# ── signing in inside the popup: email one-time code ────────────────────────

async def send_otp(db: AsyncSession, req: OAuthRequest, app: OAuthApp, email: str) -> None:
    if req.otp_sends >= MAX_OTP_SENDS:
        raise ApiError(429, "too_many_codes", "Too many codes for this sign-in — start again from the app")
    code = f"{secrets.randbelow(1_000_000):06d}"
    req.email = email.strip().lower()
    req.otp_hash, req.otp_expires_at = sha256_hex(f"{req.id}:{code}"), _now() + OTP_TTL
    req.otp_attempts, req.otp_sends = 0, req.otp_sends + 1
    db.add(req)
    org = await db.get(Organisation, app.org_id)
    await db.commit()
    subject, html = oauth_code(to=req.email, otp=code, app_name=app.name, business=org.name if org else app.name)
    await send_email(to=req.email, subject=subject, html=html,
                     body=f"Your FOID code for {app.name}: {code}\n\nIt expires in 10 minutes. If you didn't try to sign in, ignore this email.")


async def check_otp(db: AsyncSession, req: OAuthRequest, code: str) -> User | None:
    """True code → the FOID user with that email, or None (a new person). Raises on a wrong/expired code."""
    bad = ApiError(400, "invalid_code", "That code is wrong or has expired — request a new one")
    if not req.otp_hash or not req.email or cs.as_utc(req.otp_expires_at) < _now() or req.otp_attempts >= MAX_OTP_ATTEMPTS:  # type: ignore[operator]
        raise bad
    if not secrets.compare_digest(req.otp_hash, sha256_hex(f"{req.id}:{code.strip()}")):
        req.otp_attempts += 1
        db.add(req)
        await db.commit()
        raise bad
    req.otp_hash = None   # single use
    db.add(req)
    return (await db.exec(select(User).where(User.email == req.email))).first()


def guest_ticket(req: OAuthRequest) -> str:
    """A new person proved their email in this popup; this ticket lets the popup continue for them."""
    return create_ticket(f"{req.id}|{req.email}", "oauth_guest", minutes=30)


def check_guest_ticket(req: OAuthRequest, ticket: str) -> None:
    from app.core.security import decode_ticket
    try:
        rid, email = decode_ticket(ticket, "oauth_guest").split("|", 1)
    except (JWTError, ValueError):
        raise ApiError(401, "invalid_ticket", "This sign-in expired — start again from the app")
    if rid != req.id or email != req.email:
        raise ApiError(401, "invalid_ticket", "This sign-in expired — start again from the app")


# ── a FOID user: what's missing, face re-match, approve ─────────────────────

async def _existing_subject(db: AsyncSession, req: OAuthRequest, user: User) -> Subject | None:
    return (await db.exec(select(Subject).where(Subject.org_id == req.org_id, Subject.env == req.env,
                                                Subject.user_id == user.id))).first()


async def _already_shared(db: AsyncSession, req: OAuthRequest, user: User) -> bool:
    s = await _existing_subject(db, req, user)
    return bool(s and await consent.active_grants(db, req.org_id, s.id))


async def _rematched_at(db: AsyncSession, req: OAuthRequest, user: User) -> datetime | None:
    """A liveness check that passed after this sign-in started: a face match, or a new enrolment."""
    rows = (await db.exec(select(LivenessAttempt).where(
        LivenessAttempt.user_id == user.id, LivenessAttempt.passed == True,  # noqa: E712
        col(LivenessAttempt.created_at) >= cs.as_utc(req.created_at)).order_by(col(LivenessAttempt.created_at).desc()))).all()
    for a in rows:
        if a.purpose == "enrol" or (a.match_score is not None and fm.is_match(a.match_score)):
            return a.created_at
    return None


async def review(db: AsyncSession, req: OAuthRequest, user: User) -> dict[str, Any]:
    """What this person still needs to do before they can approve."""
    if req.env == "test":
        return {"missing": [], "rematch_required": False, "rematch_done": False, "already_shared": False}
    enrolled = (await db.exec(select(FaceEnrolment.id).where(FaceEnrolment.user_id == user.id))).first() is not None
    missing: list[str] = []
    if not enrolled:
        missing.append("liveness")
    if "identity" in req.scopes and user.nin_verified_at is None:
        missing.append("nin")
    shared = await _already_shared(db, req, user)
    return {"missing": missing, "rematch_required": not shared, "already_shared": shared,
            "rematch_done": await _rematched_at(db, req, user) is not None}


def _new_code(req: OAuthRequest) -> str:
    code = new_token("foid_code_", 32)
    req.code_hash, req.code_expires_at = sha256_hex(code), _now() + CODE_TTL
    req.status = "approved"
    return code


def result_for_browser(req: OAuthRequest, code: str | None, error: str | None = None) -> dict[str, Any]:
    """What the popup hands back: postMessage payload, or the redirect URL."""
    payload = {"state": req.state, **({"code": code} if code else {"error": error or "access_denied"})}
    out: dict[str, Any] = {"response_mode": req.response_mode, "payload": payload}
    if req.response_mode == "web_message":
        out["origin"] = req.origin
    else:
        sep = "&" if "?" in (req.redirect_uri or "") else "?"
        out["redirect_url"] = f"{req.redirect_uri}{sep}{urlencode(payload)}"
    return out


async def approve_user(db: AsyncSession, req: OAuthRequest, user: User, request: Request) -> dict[str, Any]:
    r = await review(db, req, user)
    if r["missing"]:
        raise ApiError(409, "steps_missing", "Finish these first: " + ", ".join(r["missing"]))
    rematched = None
    if r["rematch_required"]:
        rematched = await _rematched_at(db, req, user)
        if rematched is None:
            raise ApiError(409, "rematch_required", "Confirm it's you with a quick face check first")
    subject = await _existing_subject(db, req, user)
    if subject is None:
        subject = Subject(org_id=req.org_id, env=req.env, user_id=user.id, linked_at=_now(), link_method="foid_oauth")
    await _fill_subject(db, req, subject, user, rematched)
    g = await consent.grant(db, org_id=req.org_id, subject=subject, scopes=req.scopes, purpose="Continue with FOID",
                            source="foid_oauth", ip=request.client.host if request.client else None,
                            user_agent=request.headers.get("user-agent"))
    await db.flush()
    req.user_id, req.subject_id, req.grant_id, req.rematched_at = user.id, subject.id, g.id, rematched
    code = _new_code(req)
    db.add(req)
    cs.audit(db, org_id=req.org_id, actor_type="user", actor_id=user.id, action="foid_credential.shared",
             target_type="oauth_request", target_id=req.id, meta={"scopes": req.scopes, "via": "continue_with_foid"})
    await db.commit()
    return result_for_browser(req, code)


async def _fill_subject(db: AsyncSession, req: OAuthRequest, s: Subject, user: User, rematched: datetime | None) -> None:
    """Copy what this business may see onto its subject. Test apps: real name, sandbox everything else."""
    s.first_name, s.middle_name, s.last_name = user.first_name, user.middle_name, user.last_name
    s.updated_at = _now()
    db.add(s)
    await db.flush()
    if req.env == "test":
        s.date_of_birth, s.nin_last4, s.nin_verified = SANDBOX["date_of_birth"], SANDBOX["nin_last4"], True
        s.bvn_last4, s.bvn_verified = SANDBOX["bvn_last4"], True
        s.email, s.phone, s.liveness_passed_at = SANDBOX["email"], SANDBOX["phone"], _now()
        return
    if user.nin_verified_at is not None:
        s.date_of_birth, s.nin_hash, s.nin_last4, s.nin_verified = user.date_of_birth, user.nin_hash, user.nin_last4, True
    if user.bvn_verified_at is not None:
        s.bvn_hash, s.bvn_last4, s.bvn_verified = user.bvn_hash, user.bvn_last4, True
    s.email, s.phone = user.email, user.phone
    s.liveness_passed_at = rematched or user.liveness_verified_at
    enrolment = (await db.exec(select(FaceEnrolment).where(FaceEnrolment.user_id == user.id))).first()
    if enrolment is not None and (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == s.id))).first() is None:
        db.add(SubjectFace(subject_id=s.id, template_enc=enrolment.template_enc, face_png=enrolment.face_png,
                           face_sha256=enrolment.face_sha256, receipt=enrolment.receipt,
                           face_quality=enrolment.face_quality, model=enrolment.model))
    if rematched is not None:
        await cs.save_result(db, subject=s, check_type="reverify", status="passed", reasons=[],
                             data={"source": "continue_with_foid", "checked_at": cs.iso(rematched)}, provider="foid")


async def deny(db: AsyncSession, req: OAuthRequest) -> dict[str, Any]:
    req.status = "denied"
    db.add(req)
    await db.commit()
    return result_for_browser(req, None, "access_denied")


# ── a new person: hosted verification inside the popup, then "Save to FOID" ─

def guest_checks(req: OAuthRequest) -> list[str]:
    return ["nin", *(["liveness"] if "liveness" in req.scopes or req.env == "live" else [])]


async def guest_start(db: AsyncSession, req: OAuthRequest, *, first_name: str, last_name: str,
                      middle_name: str | None, date_of_birth: str | None) -> str:
    """Create (or reuse) the hosted verification for this person; returns its hosted URL.
    The name (as on the NIN) is what the NIN check matches against."""
    if req.verification_id:
        v = await db.get(Verification, req.verification_id)
        link = cs.open_link(v) if v else None
        if link:
            return link["hosted_url"]
    subject = Subject(org_id=req.org_id, env=req.env, email=req.email, first_name=first_name.strip(),
                      middle_name=(middle_name or "").strip() or None, last_name=last_name.strip(),
                      date_of_birth=date_of_birth or None)
    db.add(subject)
    await db.flush()
    token = new_token("vs_", 24)
    checks = guest_checks(req)
    v = Verification(org_id=req.org_id, env=req.env, subject_id=subject.id, checks=checks,
                     scopes=cs.scopes_for_checks(checks, req.scopes), purpose="Continue with FOID",
                     session_token_hash=sha256_hex(token), session_token_enc=encrypt_str(token),
                     return_url=f"{get_settings().PUBLIC_APP_URL.rstrip('/')}/oauth/continue/{req.id}",
                     metadata_={"oauth_request": req.id}, expires_at=cs.verification_expiry())
    db.add(v)
    req.verification_id, req.subject_id = v.id, subject.id
    db.add(req)
    await db.commit()
    return cs.hosted_url(token)


async def _guest_verification(db: AsyncSession, req: OAuthRequest) -> tuple[Verification, Subject]:
    v = await db.get(Verification, req.verification_id) if req.verification_id else None
    s = await db.get(Subject, req.subject_id) if req.subject_id else None
    if v is None or s is None:
        raise ApiError(409, "verification_missing", "Verify your identity first")
    return v, s


async def guest_status(db: AsyncSession, req: OAuthRequest) -> dict[str, Any]:
    v, s = await _guest_verification(db, req)
    latest = await cs.latest_results(db, v.id)
    nin_ok = latest.get("nin") is not None and latest["nin"].status == "passed"
    return {"verification_status": v.status, "outcome": v.outcome, "first_name": s.first_name,
            "can_save_to_foid": v.status == "completed" and nin_ok and s.user_id is None,
            "saved_to_foid": s.user_id is not None}


async def guest_finish(db: AsyncSession, req: OAuthRequest) -> dict[str, Any]:
    """After the hosted steps: hand the business its result (pass or fail). Declined consent → access_denied."""
    v, s = await _guest_verification(db, req)
    if v.status == "cancelled":
        return await deny(db, req)
    if v.status != "completed":
        raise ApiError(409, "verification_open", "Finish the verification steps first")
    g = (await db.exec(select(ConsentGrant).where(ConsentGrant.subject_id == s.id, ConsentGrant.status == "active")
                       .order_by(col(ConsentGrant.granted_at).desc()))).first()
    if g is None:
        return await deny(db, req)
    req.grant_id = g.id
    code = _new_code(req)
    db.add(req)
    await db.commit()
    return result_for_browser(req, code)


async def save_to_foid(db: AsyncSession, req: OAuthRequest) -> User:
    """The explicit 'Save this to FOID' tap: a FOID account from what was just verified. No password yet."""
    v, s = await _guest_verification(db, req)
    st = await guest_status(db, req)
    if not st["can_save_to_foid"]:
        raise ApiError(409, "cannot_save", "Only a completed verification with a passed NIN check can be saved to FOID")
    if (await db.exec(select(User.id).where(User.email == req.email))).first():
        raise ApiError(409, "account_exists", "There's already a FOID account with this email — sign in instead")
    if s.nin_hash and (await db.exec(select(User.id).where(User.nin_hash == s.nin_hash))).first():
        raise ApiError(409, "account_exists", "This NIN already has a FOID account — sign in with that email instead")
    now = _now()
    user = User(first_name=s.first_name or "", middle_name=s.middle_name, last_name=s.last_name or "",
                email=req.email or "", hashed_password=hash_password(secrets.token_urlsafe(32)),   # set one via "Forgot password"
                nin_hash=s.nin_hash, nin_last4=s.nin_last4, nin_verified_at=now, date_of_birth=s.date_of_birth,
                bvn_hash=s.bvn_hash if s.bvn_verified else None, bvn_last4=s.bvn_last4 if s.bvn_verified else None,
                bvn_verified_at=now if s.bvn_verified else None)
    db.add(user)
    await db.flush()
    claims = {**DEFAULT_CLAIMS, "email_verified": True, "nin_verified": True, "bvn_validated": bool(s.bvn_verified)}
    face = (await db.exec(select(SubjectFace).where(SubjectFace.subject_id == s.id))).first()
    if face is not None:
        db.add(FaceEnrolment(user_id=user.id, template_enc=face.template_enc, face_png=face.face_png,
                             face_sha256=face.face_sha256, receipt=face.receipt, face_quality=face.face_quality,
                             model=face.model, consent_at=now))
        user.liveness_verified_at = s.liveness_passed_at or now
        user.liveness_selfie_url = "/api/v1/auth/me/liveness/face"
        claims["identity_verified"] = True
    db.add(Credential(user_id=user.id, holder=f"{user.first_name} {user.last_name}", state="active", claims=claims))  # type: ignore[arg-type]
    from app.services.wallet_service import _current_month
    db.add(Wallet(user_id=user.id, free_credits=get_settings().FREE_MONTHLY_CREDITS, paid_credits=0,
                  last_free_refresh=_current_month()))
    s.user_id, s.linked_at, s.link_method = user.id, now, "foid_oauth"
    db.add(s)
    cs.audit(db, org_id=req.org_id, actor_type="user", actor_id=user.id, action="foid_account.created_from_share",
             target_type="oauth_request", target_id=req.id)
    await db.flush()
    return user


# ── the business's server exchanges the code ────────────────────────────────

async def authenticate_client(db: AsyncSession, form: dict[str, str], basic: tuple[str, str] | None,
                              token_url: str) -> tuple[OAuthApp, OAuthClientSecret | None]:
    client_id = (basic[0] if basic else None) or form.get("client_id", "")
    app = (await db.exec(select(OAuthApp).where(OAuthApp.client_id == client_id))).first() if client_id else None
    assertion = form.get("client_assertion")
    if app is None and assertion:   # private_key_jwt may carry the client id only inside the assertion
        try:
            iss = jwt.get_unverified_claims(assertion).get("iss", "")
        except JWTError:
            iss = ""
        app = (await db.exec(select(OAuthApp).where(OAuthApp.client_id == iss))).first() if iss else None
    bad = OAuthError("invalid_client", "Client authentication failed", 401)
    if app is None or app.disabled_at is not None:
        raise bad
    if app.auth_method == "private_key_jwt":
        if form.get("client_assertion_type") != ASSERTION_TYPE or not assertion or not app.public_jwk:
            raise OAuthError("invalid_client", "This app signs in with a key pair: send client_assertion (private_key_jwt)", 401)
        api_aud = f"{get_settings().API_PUBLIC_URL.rstrip('/')}/api/open/v1/oauth/token"
        try:
            claims = jwt.decode(assertion, app.public_jwk, algorithms=[app.public_jwk["alg"]],
                                options={"verify_aud": False, "require_exp": True})   # aud checked below (jose takes one)
        except JWTError:
            raise bad
        aud = claims.get("aud")
        if not ({aud} if isinstance(aud, str) else set(aud or [])) & {token_url, api_aud}:
            raise bad
        if claims.get("iss") != app.client_id or claims.get("sub") != app.client_id or not claims.get("jti"):
            raise bad
        if float(claims["exp"]) - _now().timestamp() > 300:
            raise OAuthError("invalid_client", "client_assertion must expire within 5 minutes", 401)
        return app, None
    secret = (basic[1] if basic else None) or form.get("client_secret", "")
    if not secret.startswith(oa.secret_prefix(app.env)):
        raise bad
    row = (await db.exec(select(OAuthClientSecret).where(OAuthClientSecret.secret_hash == sha256_hex(secret)))).first()
    if row is None or row.app_id != app.id or not oa.secret_usable(row):
        raise bad
    return app, row


def _pkce_ok(verifier: str, challenge: str) -> bool:
    if not _VERIFIER.match(verifier or ""):
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return secrets.compare_digest(digest, challenge)


async def exchange(db: AsyncSession, app: OAuthApp, secret: OAuthClientSecret | None, form: dict[str, str]) -> dict[str, Any]:
    if form.get("grant_type") != "authorization_code":
        raise OAuthError("unsupported_grant_type", "grant_type must be authorization_code")
    code = form.get("code", "")
    req = (await db.exec(select(OAuthRequest).where(OAuthRequest.code_hash == sha256_hex(code)))).first() if code else None
    invalid = OAuthError("invalid_grant", "The code is invalid, expired or already used")
    if req is None or req.app_id != app.id:
        raise invalid
    if req.code_used_at is not None or req.status in ("exchanged", "revoked"):
        await _revoke_replayed(db, req)    # OAuth security BCP: a reused code means it leaked
        raise invalid
    if cs.as_utc(req.code_expires_at) < _now():   # type: ignore[operator]
        raise invalid
    if req.response_mode == "query" and form.get("redirect_uri") != req.redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri doesn't match the one used to start sign-in")
    if not _pkce_ok(form.get("code_verifier", ""), req.code_challenge):
        raise OAuthError("invalid_grant", "PKCE check failed (code_verifier)")
    now = _now()
    req.code_used_at, req.status = now, "exchanged"
    db.add(req)
    if secret is not None:
        secret.last_used_at = now
        db.add(secret)
    subject = await db.get(Subject, req.subject_id) if req.subject_id else None
    if subject is None:
        raise invalid
    cs.record_usage(db, org_id=req.org_id, env=req.env, check_type="foid_sign_in", subject_id=subject.id, verification_id=None)
    out = await result(db, req, subject)
    await db.commit()
    return out


async def result(db: AsyncSession, req: OAuthRequest, subject: Subject) -> dict[str, Any]:
    s = await cs.serialize_subject(db, subject)
    checks = (await db.exec(select(CheckResult).where(CheckResult.subject_id == subject.id)
                            .order_by(col(CheckResult.created_at).desc()).limit(20))).all()
    return {
        "object": "foid_sign_in",
        "env": req.env,
        "sandbox": req.env == "test",
        "nonce": req.nonce,
        "subject_id": subject.id,
        "scopes": req.scopes,
        "foid_account": subject.user_id is not None,
        "face_rematched_at": cs.iso(req.rematched_at),
        "subject": s,
        "checks": [cs.serialize_check(c) for c in checks] if "identity" in req.scopes or "liveness" in req.scopes else [],
    }


async def _revoke_replayed(db: AsyncSession, req: OAuthRequest) -> None:
    if req.status != "revoked":
        req.status = "revoked"
        db.add(req)
        g = await db.get(ConsentGrant, req.grant_id) if req.grant_id else None
        if g is not None and g.status == "active":
            g.status, g.revoked_at, g.revoked_by = "revoked", _now(), "system"
            db.add(g)
        cs.audit(db, org_id=req.org_id, actor_type="system", actor_id=None, action="oauth.code_replayed",
                 target_type="oauth_request", target_id=req.id)
        from app.services import console_inbox
        await console_inbox.notify(db, req.org_id, "security", "A sign-in code was used twice",
                                   "FOID cancelled that sign-in because its one-time code was reused — it may have leaked. "
                                   "Check that your server exchanges each code once.", link="/apps", min_role="developer")
        await db.commit()

