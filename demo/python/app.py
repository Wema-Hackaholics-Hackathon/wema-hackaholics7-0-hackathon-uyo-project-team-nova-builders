"""Harbor demo — Python backend.

A pretend business ("Harbor") integrating FOID with the `foid` Python SDK, installed from
vendor/foid-0.1.0-py3-none-any.whl exactly like a package from PyPI. It serves the React app
(../dist) and a small JSON API under /api. Every /api route is one SDK call, so clicking through
the UI exercises the whole SDK.

    uv run uvicorn app:app --host 127.0.0.1 --port 3100
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import foid
from foid import Foid, FoidError, WebhookError, create_pkce
from foid.keypair import generate_keypair

HERE = Path(__file__).resolve().parent


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def load_dotenv(path: Path) -> None:
    """Outside Docker, read ../.env (Docker passes the same values with env_file)."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


load_dotenv(HERE.parent / ".env")
if env("DEMO_ENV_FILE"):              # docker-compose: settings written by the backend's first-boot seed
    load_dotenv(Path(env("DEMO_ENV_FILE")))

API_URL = env("FOID_API_URL", "http://localhost:8000")
FOID_URL = env("FOID_APP_URL", "http://localhost:5173")
WEBHOOK_SECRET = env("FOID_WEBHOOK_SECRET") or env("FOID_WEBHOOK_SECRET_PYTHON")
KEYS_DIR = Path(env("DEMO_KEYS_DIR", str(HERE.parent / "keys")))
DIST_DIR = Path(env("DEMO_DIST_DIR", str(HERE.parent / "dist")))
PRIVATE_KEY = KEYS_DIR / "private_key.pem"
PUBLIC_JWK = KEYS_DIR / "public_jwk.json"

# One client per credential. The API key is for the Open API; the client secret / key pair only
# exchange sign-in codes for their own app.
api = Foid(api_key=env("FOID_API_KEY") or None, base_url=API_URL)
secret_client = Foid(client_id=env("FOID_CLIENT_ID") or None,
                     client_secret=env("FOID_CLIENT_SECRET") or None, base_url=API_URL)


def keypair_client() -> Foid:
    """Built per exchange so a key generated from the UI works without a restart."""
    pem = PRIVATE_KEY.read_text() if PRIVATE_KEY.is_file() else None
    kid = env("FOID_KEY_ID") or (json.loads(PUBLIC_JWK.read_text()).get("kid") if PUBLIC_JWK.is_file() else None)
    return Foid(client_id=env("FOID_KEYPAIR_CLIENT_ID") or None, private_key_pem=pem, key_id=kid, base_url=API_URL)


pending: dict[str, dict[str, Any]] = {}       # server-led sign-in: state -> verifier, nonce, method
events: deque[dict[str, Any]] = deque(maxlen=100)

app = FastAPI(title="Harbor demo (Python SDK)")


class DemoError(Exception):
    def __init__(self, status: int, code: str, message: str, body: Any = None) -> None:
        self.status, self.code, self.message, self.body = status, code, message, body


@app.exception_handler(DemoError)
async def demo_error(_: Request, exc: DemoError) -> JSONResponse:
    return JSONResponse({"error": {"status": exc.status, "code": exc.code, "message": exc.message, "body": exc.body}},
                        status_code=exc.status)


def sdk(call: Any) -> Any:
    """Run an SDK call; turn its errors into one JSON shape the UI shows."""
    try:
        return call()
    except FoidError as e:
        raise DemoError(e.status, e.code, e.message, e.body)
    except (ValueError, RuntimeError) as e:            # missing key / secret / client id
        raise DemoError(400, "not_configured", str(e))
    except httpx.HTTPError as e:
        raise DemoError(502, "foid_unreachable", f"Can't reach FOID at {API_URL}: {e}")


async def body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def clean(d: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: d[k] for k in keys if d.get(k) not in (None, "", [])}


PERSON = ("customer_ref", "subject_id", "first_name", "middle_name", "last_name", "date_of_birth", "email", "phone")


# ── setup ─────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "backend": "python",
        "sdk": {"package": "foid", "version": foid.__version__},
        "apiUrl": API_URL,
        "foidUrl": FOID_URL,
        "clientId": env("FOID_CLIENT_ID"),
        "keypairClientId": env("FOID_KEYPAIR_CLIENT_ID"),
        "has": {
            "apiKey": bool(env("FOID_API_KEY")),
            "clientSecret": bool(env("FOID_CLIENT_SECRET")),
            "privateKey": PRIVATE_KEY.is_file(),
            "webhookSecret": bool(WEBHOOK_SECRET),
        },
    }


@app.get("/api/keypair")
def get_keypair() -> dict[str, Any]:
    return {"exists": PRIVATE_KEY.is_file(),
            "public_jwk": json.loads(PUBLIC_JWK.read_text()) if PUBLIC_JWK.is_file() else None}


@app.post("/api/keypair")
def make_keypair() -> dict[str, Any]:
    """foid.keypair.generate_keypair(): the private key stays in keys/, the public JWK goes to the console."""
    if PRIVATE_KEY.is_file():
        raise DemoError(409, "key_exists", "keys/private_key.pem already exists. Delete it to make a new pair.")
    pem, jwk = generate_keypair()
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_KEY.write_text(pem)
    PRIVATE_KEY.chmod(0o600)
    PUBLIC_JWK.write_text(json.dumps(jwk, indent=2))
    return {"exists": True, "public_jwk": jwk}


# ── Open API (API key) ───────────────────────────────────────────────────────

@app.get("/api/ping")
def ping() -> Any:
    return sdk(lambda: api.request("GET", "/ping"))


@app.post("/api/verifications")
async def create_verification(request: Request) -> Any:
    b = await body(request)
    payload = clean(b, "checks", "scopes", "purpose", "return_url", "metadata", *PERSON)
    key = b.get("idempotency_key") or None
    return sdk(lambda: api.create_verification(**payload, idempotency_key=key))


@app.get("/api/verifications")
def list_verifications(status: str = "", customer_ref: str = "") -> Any:
    params = clean({"status": status, "customer_ref": customer_ref}, "status", "customer_ref")
    return sdk(lambda: api.request("GET", "/verifications", params=params or None))


@app.get("/api/verifications/{vid}")
def get_verification(vid: str) -> Any:
    return sdk(lambda: api.get_verification(vid))


@app.post("/api/verifications/{vid}/cancel")
def cancel_verification(vid: str) -> Any:
    return sdk(lambda: api.request("POST", f"/verifications/{vid}/cancel"))


@app.post("/api/checks/{kind}")
async def check(kind: str, request: Request) -> Any:
    if kind not in ("nin", "bvn"):
        raise DemoError(404, "not_found", "Use /api/checks/nin or /api/checks/bvn")
    b = await body(request)
    payload = {"number": b.get("number", ""),
               "consent": {"obtained": bool(b.get("consent_obtained")), "purpose": b.get("purpose") or "Account opening"},
               **clean(b, *PERSON)}
    fn = api.check_nin if kind == "nin" else api.check_bvn
    return sdk(lambda: fn(**payload))


@app.get("/api/subjects")
def list_subjects(customer_ref: str = "") -> Any:
    return sdk(lambda: api.request("GET", "/subjects", params={"customer_ref": customer_ref} if customer_ref else None))


@app.get("/api/subjects/{sid}")
def get_subject(sid: str) -> Any:
    return sdk(lambda: api.get_subject(sid))


@app.get("/api/subjects/{sid}/checks")
def subject_checks(sid: str) -> Any:
    return sdk(lambda: api.request("GET", f"/subjects/{sid}/checks"))


@app.get("/api/subjects/{sid}/trust-report")
def trust_report(sid: str) -> Any:
    return sdk(lambda: api.request("GET", f"/subjects/{sid}/trust-report"))


@app.delete("/api/subjects/{sid}")
def delete_subject(sid: str) -> Any:
    sdk(lambda: api.request("DELETE", f"/subjects/{sid}"))
    return {"deleted": sid}


# ── Continue with FOID ──────────────────────────────────────────────────────

def client_for(method: str) -> Foid:
    return keypair_client() if method == "keypair" else secret_client


@app.post("/api/signin/start")
async def signin_start(request: Request) -> dict[str, Any]:
    """Server-led sign-in: create_pkce() here, keep the verifier + nonce, hand the browser a URL."""
    b = await body(request)
    method = "keypair" if b.get("method") == "keypair" else "secret"
    client_id = env("FOID_KEYPAIR_CLIENT_ID") if method == "keypair" else env("FOID_CLIENT_ID")
    if not client_id:
        raise DemoError(400, "not_configured", f"Set {'FOID_KEYPAIR_CLIENT_ID' if method == 'keypair' else 'FOID_CLIENT_ID'} in .env")
    p = create_pkce()
    q = {"client_id": client_id, "scope": b.get("scope") or "profile", "state": p["state"], "nonce": p["nonce"],
         "code_challenge": p["code_challenge"], "code_challenge_method": "S256"}
    redirect_uri = b.get("redirect_uri")
    if redirect_uri:
        q.update(response_mode="query", redirect_uri=redirect_uri)
    else:
        q.update(response_mode="web_message", origin=b.get("origin", ""))
    pending[p["state"]] = {"verifier": p["code_verifier"], "nonce": p["nonce"], "method": method,
                           "redirect_uri": redirect_uri, "at": time.time()}
    for s in [s for s, v in pending.items() if time.time() - v["at"] > 600]:
        pending.pop(s, None)
    return {"authorize_url": f"{FOID_URL.rstrip('/')}/oauth/authorize?{urlencode(q)}", "state": p["state"]}


@app.post("/api/signin/exchange")
async def signin_exchange(request: Request) -> dict[str, Any]:
    """foid.oauth.exchange(code, code_verifier): the one-time code -> who signed in and what they shared."""
    b = await body(request)
    code = b.get("code") or ""
    started = pending.pop(b.get("state") or "", None) if not b.get("code_verifier") else None
    if started:
        method, verifier, redirect_uri, nonce = started["method"], started["verifier"], started["redirect_uri"], started["nonce"]
    else:
        method, verifier, redirect_uri, nonce = b.get("method", "secret"), b.get("code_verifier"), b.get("redirect_uri"), b.get("nonce")
    if not verifier:
        raise DemoError(400, "missing_verifier", "No code_verifier for this sign-in (or the server-led state expired)")
    result = sdk(lambda: client_for(method).oauth.exchange(code, verifier, redirect_uri=redirect_uri or None))
    return {"backend": "python", "auth": "private_key_jwt" if method == "keypair" else "client_secret",
            "server_led": bool(started), "nonce_ok": (result.get("nonce") == nonce) if nonce else None,
            "result": result}


# ── webhooks ─────────────────────────────────────────────────────────────────

@app.post("/webhooks/foid")
async def webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    header = request.headers.get("foid-signature", "")
    if not WEBHOOK_SECRET:
        events.appendleft({"verified": False, "error": "FOID_WEBHOOK_SECRET is not set", "at": time.time()})
        return JSONResponse({"error": "webhook secret not configured"}, status_code=500)
    try:
        event = api.webhooks.verify(raw, header, WEBHOOK_SECRET)
    except WebhookError as e:
        events.appendleft({"verified": False, "error": str(e), "at": time.time()})
        return JSONResponse({"error": str(e)}, status_code=400)
    events.appendleft({"verified": True, "at": time.time(), "event": event})
    return JSONResponse({"received": True})


@app.get("/api/webhooks")
def webhook_log() -> dict[str, Any]:
    return {"secret_configured": bool(WEBHOOK_SECRET), "events": list(events)}


@app.delete("/api/webhooks")
def clear_webhooks() -> dict[str, Any]:
    events.clear()
    return {"cleared": True}


# ── the React app ───────────────────────────────────────────────────────────

if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Any:
    if path.startswith("api/"):
        raise DemoError(404, "not_found", f"No route /{path}")
    f = (DIST_DIR / path).resolve()
    if path and f.is_file() and DIST_DIR.resolve() in f.parents:
        return FileResponse(f)
    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"message": "API is up. Build the UI (npm run build) or use npm run dev."})
