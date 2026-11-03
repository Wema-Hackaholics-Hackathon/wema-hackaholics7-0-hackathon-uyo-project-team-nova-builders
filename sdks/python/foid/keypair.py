"""Key pair for private_key_jwt: your server signs each code exchange; FOID only holds the public key."""

from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Any


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _crypto() -> Any:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Key pairs need the 'cryptography' package: pip install 'foid[keypair]'") from e
    return hashes, serialization, ec, utils


def generate_keypair() -> tuple[str, dict[str, str]]:
    """(private key PEM — keep it secret, public JWK — paste it in FOID Console → Sign-in apps)."""
    hashes, serialization, ec, _ = _crypto()
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    nums = key.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "x": _b64url(nums.x.to_bytes(32, "big")), "y": _b64url(nums.y.to_bytes(32, "big")),
           "alg": "ES256", "kid": secrets.token_hex(4)}
    return pem, jwk


def client_assertion(private_key_pem: str, client_id: str, audience: str, kid: str | None = None) -> str:
    """A 60-second ES256 JWT proving this request comes from the key holder."""
    hashes, serialization, ec, utils = _crypto()
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    header = {"alg": "ES256", "typ": "JWT", **({"kid": kid} if kid else {})}
    now = int(time.time())
    claims = {"iss": client_id, "sub": client_id, "aud": audience, "iat": now, "exp": now + 60, "jti": secrets.token_hex(16)}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}".encode()
    r, s = utils.decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    return f"{signing_input.decode()}.{_b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
