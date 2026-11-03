"""Rules for 'Continue with FOID' apps: credentials, allowed origins / redirect URIs, public keys.

Live apps: https only, exact origins and redirect URIs, no localhost.
Test apps: the same, plus http://localhost and http://127.0.0.1 on any port (registered or not —
the loopback rule is applied again at sign-in time, see is_loopback).
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from jose import jwk
from jose.utils import base64url_decode

from app.core.api_errors import ApiError
from app.core.crypto import sha256_hex
from app.models import OAuthApp, OAuthClientSecret
from app.services import checks_service as cs
from app.services.consent_service import SCOPES

_ALPHABET = string.ascii_letters + string.digits
APP_SCOPES: dict[str, str] = SCOPES   # "profile" is always included
MAX_APPS_PER_ENV = 10
MAX_URLS = 10
ROTATION_OVERLAP_HOURS = 24


def _rand(n: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def new_client_id(env: str) -> str:
    return f"foid_app_{env}_{_rand(24)}"


def secret_prefix(env: str) -> str:
    return f"foid_cs_{env}_"


def new_secret(env: str) -> tuple[str, str, str]:
    """(raw, hint, sha256). Only hint + hash are stored; raw is shown once."""
    raw = secret_prefix(env) + _rand(40)
    return raw, f"{secret_prefix(env)}{raw[-40:][:2]}…{raw[-2:]}", sha256_hex(raw)


def is_loopback(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1")


def _bad(field: str, msg: str) -> ApiError:
    return ApiError(422, "invalid_app_config", msg, param=field)


def clean_origin(env: str, value: str) -> str:
    v = value.strip().rstrip("/")
    p = urlsplit(v)
    if not p.scheme or not p.hostname or p.path or p.query or p.fragment or p.username:
        raise _bad("origins", f"{value!r} isn't an origin — use scheme + host (+ port), e.g. https://app.example.com")
    if p.scheme == "https" or (env == "test" and is_loopback(v)):
        return f"{p.scheme}://{p.netloc.lower()}"
    raise _bad("origins", f"{value!r}: live apps need https" if env == "live" else
               f"{value!r}: use https, or http://localhost / 127.0.0.1 for local testing")


def clean_redirect(env: str, value: str) -> str:
    v = value.strip()
    p = urlsplit(v)
    if not p.scheme or not p.hostname or p.fragment or p.username:
        raise _bad("redirect_uris", f"{value!r} isn't a valid redirect URI (no #fragment allowed)")
    if p.scheme == "https" or (env == "test" and is_loopback(v)):
        return v
    raise _bad("redirect_uris", f"{value!r}: live apps need https" if env == "live" else
               f"{value!r}: use https, or http://localhost / 127.0.0.1 for local testing")


def clean_list(env: str, values: list[str], kind: str) -> list[str]:
    if len(values) > MAX_URLS:
        raise _bad(kind, f"At most {MAX_URLS} {kind.replace('_', ' ')}")
    fn = clean_origin if kind == "origins" else clean_redirect
    return list(dict.fromkeys(fn(env, v) for v in values if v.strip()))


def clean_scopes(values: list[str]) -> list[str]:
    bad = [s for s in values if s not in APP_SCOPES]
    if bad:
        raise _bad("scopes", f"Unknown scope(s): {', '.join(bad)}. Allowed: {', '.join(APP_SCOPES)}")
    return ["profile", *sorted(set(values) - {"profile"})]


def clean_public_jwk(value: dict[str, Any]) -> dict[str, Any]:
    """An EC P-256 or RSA (≥ 2048-bit) public key as a JWK, for private_key_jwt. Private parts are refused."""
    if any(k in value for k in ("d", "p", "q", "dp", "dq", "qi")):
        raise _bad("public_jwk", "That's a PRIVATE key — paste only the public key. Keep the private key on your server.")
    kty = value.get("kty")
    if kty == "EC" and value.get("crv") != "P-256":
        raise _bad("public_jwk", "EC keys must use the P-256 curve (ES256)")
    if kty not in ("EC", "RSA"):
        raise _bad("public_jwk", "Use an EC P-256 (ES256) or RSA (RS256) public key in JWK format")
    alg = "ES256" if kty == "EC" else "RS256"
    try:
        jwk.construct(value, alg).to_pem()
    except Exception:  # jose raises several types for malformed keys
        raise _bad("public_jwk", "That JWK couldn't be read as a public key")
    if kty == "RSA" and len(base64url_decode(str(value.get("n", "")).encode())) * 8 < 2048:
        raise _bad("public_jwk", "RSA keys must be at least 2048 bits")
    keep = ("kty", "crv", "x", "y") if kty == "EC" else ("kty", "n", "e")
    return {**{k: value[k] for k in keep}, "alg": alg, **({"kid": str(value["kid"])} if value.get("kid") else {})}


def secret_usable(s: OAuthClientSecret, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return s.revoked_at is None and (s.expires_at is None or s.expires_at > now)


def app_out(app: OAuthApp, secrets_: list[OAuthClientSecret]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "id": app.id, "env": app.env, "name": app.name, "client_id": app.client_id,
        "origins": app.origins, "redirect_uris": app.redirect_uris, "scopes": app.scopes,
        "auth_method": app.auth_method, "public_jwk": app.public_jwk,
        "loopback_allowed": app.env == "test",
        "created_at": cs.iso(app.created_at),
        "secrets": [{"id": s.id, "hint": s.hint, "created_at": cs.iso(s.created_at), "expires_at": cs.iso(s.expires_at),
                     "last_used_at": cs.iso(s.last_used_at)}
                    for s in sorted(secrets_, key=lambda x: x.created_at, reverse=True) if secret_usable(s, now)],
    }
