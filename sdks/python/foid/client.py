"""FOID API client (sync). Server-side only — never ship secrets to a browser or mobile app."""

from __future__ import annotations

from typing import Any

import httpx

from .keypair import client_assertion
from .webhooks import verify_webhook

DEFAULT_BASE_URL = "https://api.foid.ng"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


class FoidError(Exception):
    def __init__(self, status: int, code: str, message: str, body: Any = None) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.body = status, code, message, body


def _error(r: httpx.Response) -> FoidError:
    try:
        body = r.json()
    except ValueError:
        return FoidError(r.status_code, "http_error", r.text[:200])
    if "error" in body and isinstance(body["error"], str):      # OAuth format
        return FoidError(r.status_code, body["error"], body.get("error_description", ""), body)
    err = body.get("error") or {}
    return FoidError(r.status_code, err.get("code", "http_error"), err.get("message", str(body)), body)


class _OAuth:
    def __init__(self, foid: "Foid") -> None:
        self._f = foid

    def exchange(self, code: str, code_verifier: str, redirect_uri: str | None = None) -> dict[str, Any]:
        """Swap the one-time code from the sign-in popup for the person's result. Do this once, within 60 s."""
        f = self._f
        if not f.client_id:
            raise ValueError("client_id is required")
        url = f"{f.base_url}/api/open/v1/oauth/token"
        form = {"grant_type": "authorization_code", "code": code, "code_verifier": code_verifier,
                **({"redirect_uri": redirect_uri} if redirect_uri else {})}
        auth = None
        if f.private_key_pem:
            form.update(client_id=f.client_id, client_assertion_type=ASSERTION_TYPE,
                        client_assertion=client_assertion(f.private_key_pem, f.client_id, url, f.key_id))
        elif f.client_secret:
            auth = (f.client_id, f.client_secret)
        else:
            raise ValueError("Pass client_secret, or private_key_pem for a key-pair app")
        r = f._http.post(url, data=form, auth=auth)
        if r.status_code != 200:
            raise _error(r)
        return r.json()


class _Webhooks:
    @staticmethod
    def verify(payload: bytes | str, header: str, secret: str, tolerance: int = 300) -> dict[str, Any]:
        return verify_webhook(payload, header, secret, tolerance)


class Foid:
    """client_id + client_secret (or private_key_pem): Continue with FOID.  api_key: everything else."""

    def __init__(self, *, api_key: str | None = None, client_id: str | None = None, client_secret: str | None = None,
                 private_key_pem: str | None = None, key_id: str | None = None,
                 base_url: str = DEFAULT_BASE_URL, timeout: float = 15.0) -> None:
        self.api_key, self.client_id, self.client_secret = api_key, client_id, client_secret
        self.private_key_pem, self.key_id = private_key_pem, key_id
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": "foid-python/0.1.0"})
        self.oauth = _OAuth(self)
        self.webhooks = _Webhooks()

    # ── Open API (API key) ──────────────────────────────────────────────────
    def request(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None,
                idempotency_key: str | None = None) -> Any:
        if not self.api_key:
            raise ValueError("api_key is required for the Open API")
        headers = {"Authorization": f"Bearer {self.api_key}", **({"Idempotency-Key": idempotency_key} if idempotency_key else {})}
        r = self._http.request(method, f"{self.base_url}/api/open/v1{path}", json=json, params=params, headers=headers)
        if r.status_code >= 400:
            raise _error(r)
        return r.json() if r.content else None

    def get_subject(self, subject_id: str) -> dict[str, Any]:
        return self.request("GET", f"/subjects/{subject_id}")

    def create_verification(self, **body: Any) -> dict[str, Any]:
        key = body.pop("idempotency_key", None)
        return self.request("POST", "/verifications", json=body, idempotency_key=key)

    def get_verification(self, verification_id: str) -> dict[str, Any]:
        return self.request("GET", f"/verifications/{verification_id}")

    def check_nin(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/checks/nin", json=body)

    def check_bvn(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/checks/bvn", json=body)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Foid":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
