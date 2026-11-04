"""Generate docs/api/reference.md from the backend itself, so the reference can't drift from the code.

    cd docs && pnpm api          # = cd backend && uv run python ../docs/scripts/gen_api_reference.py

1. Reads FastAPI's OpenAPI schema and keeps only the public Open API (/api/open/v1/*).
2. Boots the app against a throwaway SQLite database (external services blanked), creates a test
   business + API key + sign-in app, and calls every endpoint once — the responses become the
   examples. Everything runs in-process; nothing touches the network or a real database.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

TMP = tempfile.mkdtemp(prefix="foid-docs-api-")
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{TMP}/docs.db", "ENV": "test", "SECRET_KEY": "docs-generator",
    "RESEND_API_KEY": "", "GROQ_API_KEY": "", "BACHS_API_KEY": "", "BACHS_WEBHOOK_SECRET": "",
    "MONO_SECRET_KEY": "", "MONO_PUBLIC_KEY": "", "REDIS_URL": "", "PUBLIC_APP_URL": "https://usefoid.pages.dev",
})
sys.path.insert(0, str(Path.cwd()))      # run from backend/

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.config import _get_session_factory, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import oauth_flow, user_signin  # noqa: E402
from app.utils.limiter import limiter  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "api" / "reference.md"
OPEN = "/api/open/v1"
limiter.enabled = False

# Section order + wording for each endpoint (summary comes from here, details from the code's docstring).
SECTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Connection", "", [("GET", "/ping")]),
    ("Verifications", "Hosted verification: create a link, send the person to it, read the result.", [
        ("POST", "/verifications"), ("GET", "/verifications"), ("GET", "/verifications/{verification_id}"),
        ("POST", "/verifications/{verification_id}/cancel")]),
    ("Checks", "Server-to-server checks. You attest you collected the person's consent.", [
        ("POST", "/checks/nin"), ("POST", "/checks/bvn"), ("POST", "/checks/nin-document")]),
    ("Subjects", "The people you have verified. Every read goes through the person's consent.", [
        ("GET", "/subjects"), ("GET", "/subjects/{subject_id}"), ("GET", "/subjects/{subject_id}/checks"),
        ("GET", "/subjects/{subject_id}/trust-report"), ("DELETE", "/subjects/{subject_id}")]),
    ("Continue with FOID", "Exchange the one-time code from the sign-in popup. Client credentials, not the API key.", [
        ("POST", "/oauth/token")]),
]


def anchor(method: str, path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{method} {path}".lower()).strip("-")


def resolve(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    return schema


def type_of(s: dict[str, Any], spec: dict[str, Any]) -> str:
    if "anyOf" in s:
        kinds = [type_of(x, spec) for x in s["anyOf"] if x.get("type") != "null"]
        return " \\| ".join(dict.fromkeys(kinds)) or "null"
    if "$ref" in s:
        return "object"
    if "enum" in s:
        return " \\| ".join(f"`{v}`" for v in s["enum"])
    if "const" in s:
        return f"`{json.dumps(s['const'])}`"
    t = s.get("type", "any")
    if t == "array":
        item = s.get("items", {})
        inner = " \\| ".join(f"`{v}`" for v in item["enum"]) if "enum" in item else type_of(item, spec)
        return f"array of {inner}"
    if s.get("format") in ("email", "binary", "date"):
        return f"{t} ({s['format']})"
    return t


def fields_table(schema: dict[str, Any], spec: dict[str, Any], prefix: str = "") -> list[str]:
    schema = resolve(schema, spec)
    required = set(schema.get("required", []))
    rows: list[str] = []
    for name, prop in schema.get("properties", {}).items():
        notes = []
        p = prop
        for x in prop.get("anyOf", []):
            if "$ref" in x:
                p = x
        if prop.get("description"):
            notes.append(prop["description"])
        for k, label in (("minLength", "min length"), ("maxLength", "max length"), ("minItems", "min items"), ("pattern", "pattern")):
            v = prop.get(k) or next((x.get(k) for x in prop.get("anyOf", []) if x.get(k) is not None), None)
            if v is not None:
                notes.append(f"{label} `{v}`" if k == "pattern" else f"{label} {v}")
        if "default" in prop and prop["default"] not in (None, [], {}):
            notes.append(f"default `{json.dumps(prop['default'])}`")
        rows.append(f"| `{prefix}{name}` | {type_of(prop, spec)} | {'yes' if name in required else ''} | {'; '.join(notes)} |")
        if "$ref" in p:                       # nested object: list its fields too
            rows += fields_table(p, spec, prefix=f"{prefix}{name}.")
    return rows


def pkce() -> tuple[str, str]:
    v = secrets.token_urlsafe(48)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


async def sql(statement: str, **params: Any) -> None:
    async with _get_session_factory()() as db:
        await db.execute(text(statement), params)
        await db.commit()


def scrub(value: Any) -> Any:
    """Make examples stable-looking: keep shapes, replace generated secrets/tokens."""
    if isinstance(value, dict):
        return {k: ("vs_…" if k == "client_token" and v else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"/verify/vs_[A-Za-z0-9_-]+", "/verify/vs_…", value)
    return value


async def record() -> dict[tuple[str, str], tuple[int, Any, Any]]:
    """Call every endpoint once; returns {(method, path-template): (status, request_example, response)}."""
    mails: list[dict[str, Any]] = []

    async def fake_mail(**kw: Any) -> bool:
        mails.append(kw)
        return True
    oauth_flow.send_email = fake_mail          # type: ignore[assignment]
    user_signin.send_email = fake_mail         # type: ignore[assignment]

    await init_db()
    ex: dict[tuple[str, str], tuple[int, Any, Any]] = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://docs") as c:
        r = await c.post("/api/v1/console/auth/signup", json={"first_name": "Ada", "last_name": "Developer",
                         "email": "dev@acme.example", "password": "Passw0rd!x", "company_name": "Acme Wallet"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        await sql("UPDATE console_users SET email_verified_at=created_at")
        org = (await c.get("/api/v1/business/organisations", headers=h)).json()[0]["id"]
        key = (await c.post(f"/api/v1/business/organisations/{org}/api-keys", json={"env": "test"}, headers=h)).json()["secret"]
        k = {"Authorization": f"Bearer {key}"}

        async def call(method: str, tpl: str, path: str, body: Any = None, **kw: Any) -> Any:
            r = await c.request(method, OPEN + path, headers={**k, **kw.pop("headers", {})}, json=body, **kw)
            data = r.json() if r.content else None
            ex[(method, tpl)] = (r.status_code, body, scrub(data))
            return data

        await call("GET", "/ping", "/ping")
        v = await call("POST", "/verifications", "/verifications", {
            "checks": ["nin", "liveness"], "purpose": "Open a wallet", "customer_ref": "cust_1001",
            "first_name": "Ada", "last_name": "Obi", "return_url": "https://acme.example/onboarding/done"},
            headers={"Idempotency-Key": "onboard-cust_1001"})
        await call("GET", "/verifications", "/verifications?status=pending")
        await call("GET", "/verifications/{verification_id}", f"/verifications/{v['id']}")
        await call("POST", "/verifications/{verification_id}/cancel", f"/verifications/{v['id']}/cancel")
        chk = {"number": "12345678901", "first_name": "Ada", "last_name": "Obi", "date_of_birth": "1994-03-12",
               "customer_ref": "cust_1001", "consent": {"obtained": True, "purpose": "Account opening"}}
        nin = await call("POST", "/checks/nin", "/checks/nin", chk)
        await call("POST", "/checks/bvn", "/checks/bvn", chk)
        sid = nin["subject_id"]
        await call("GET", "/subjects", "/subjects?customer_ref=cust_1001")
        await call("GET", "/subjects/{subject_id}", f"/subjects/{sid}")
        await call("GET", "/subjects/{subject_id}/checks", f"/subjects/{sid}/checks")
        await call("GET", "/subjects/{subject_id}/trust-report", f"/subjects/{sid}/trust-report")
        await call("DELETE", "/subjects/{subject_id}", f"/subjects/{sid}")

        # Continue with FOID: a real sign-in through the popup API, then the token exchange.
        app_ = (await c.post(f"/api/v1/business/organisations/{org}/apps", headers=h, json={
            "env": "test", "name": "Acme web", "origins": ["https://acme.example"], "scopes": ["identity", "contact"]})).json()
        await c.post("/api/v1/auth/signup", json={"first_name": "Chiamaka", "last_name": "Eze", "nin": "70123456789",
                     "email": "chiamaka@person.example", "password": "Passw0rd!x"})
        verifier, challenge = pkce()
        view = (await c.post("/api/v1/oauth/authorize", json={
            "client_id": app_["client_id"], "response_mode": "web_message", "origin": "https://acme.example",
            "scope": "identity contact", "state": "st_8f2c1a", "nonce": "n_51b7", "code_challenge": challenge,
            "code_challenge_method": "S256"})).json()
        await c.post(f"/api/v1/oauth/requests/{view['id']}/email", json={"email": "chiamaka@person.example"})
        otp = re.search(r"(\d{6})", mails[-1]["subject"]).group(1)  # type: ignore[union-attr]
        tok = (await c.post(f"/api/v1/oauth/requests/{view['id']}/email/verify", json={"code": otp})).json()
        code = (await c.post(f"/api/v1/oauth/requests/{view['id']}/approve",
                             headers={"Authorization": f"Bearer {tok['access_token']}"})).json()["payload"]["code"]
        form = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier}
        r = await c.post(f"{OPEN}/oauth/token", data=form, auth=(app_["client_id"], app_["client_secret"]))
        ex[("POST", "/oauth/token")] = (r.status_code, {**form, "code": "…", "code_verifier": "…"}, scrub(r.json()))
    return ex


def render(spec: dict[str, Any], ex: dict[tuple[str, str], tuple[int, Any, Any]]) -> str:
    out = [
        "---", "outline: [2, 3]", "---", "",
        "# Endpoints", "",
        "<!-- Generated by docs/scripts/gen_api_reference.py — don't edit by hand; run `pnpm api` in docs/. -->", "",
        "Every endpoint of the Open API, generated from the FOID backend. The examples are real responses from a",
        "test-mode run (sandbox data). Base URL: `https://foid-iy7u.onrender.com/api/open/v1` (locally `http://localhost:8000/api/open/v1`).",
        "Authenticate with `Authorization: Bearer FOID_TEST_…` (or `FOID_LIVE_…`) — except the token endpoint, which",
        "uses the sign-in app's client credentials. See [Overview](./) for auth, errors and limits.", "",
    ]
    for title, intro, eps in SECTIONS:
        out += [f"## {title}", ""] + ([intro, ""] if intro else [])
        for method, path in eps:
            op = spec["paths"][OPEN + path][method.lower()]
            out += [f"### {method} `{path}` {{#{anchor(method, path)}}}", ""]
            doc = (op.get("description") or "").strip()
            if doc:
                out += [doc.split("\n\n")[0].replace("\n", " "), ""]
            params = [p for p in op.get("parameters", []) if p.get("in") in ("path", "query")]
            if params:
                out += ["| Parameter | In | Type | Required |", "|---|---|---|---|"]
                out += [f"| `{p['name']}` | {p['in']} | {type_of(p.get('schema', {}), spec)} | {'yes' if p.get('required') else ''} |" for p in params]
                out.append("")
            if method == "POST" and path == "/verifications" or path.startswith("/checks/nin") and path.endswith("nin") or path == "/checks/bvn":
                out += ["Optional header: `Idempotency-Key` — repeat the same request safely (same key + same body = same result).", ""]
            body = op.get("requestBody", {}).get("content", {})
            for ctype, media in body.items():
                schema = media.get("schema", {})
                if path == "/oauth/token":
                    break
                rows = fields_table(schema, spec)
                if rows:
                    kind = "multipart form" if "multipart" in ctype else "JSON body"
                    out += [f"**{kind}**", "", "| Field | Type | Required | Notes |", "|---|---|---|---|", *rows, ""]
            if path == "/oauth/token":
                out += [
                    "**Form body** (`application/x-www-form-urlencoded` or JSON)", "",
                    "| Field | Required | Notes |", "|---|---|---|",
                    "| `grant_type` | yes | `authorization_code` |",
                    "| `code` | yes | The one-time code from the popup. Single use, expires after 60 seconds. |",
                    "| `code_verifier` | yes | The PKCE verifier that matches the `code_challenge` used to start sign-in. |",
                    "| `redirect_uri` | redirect mode | Exactly the one used to start sign-in (`response_mode=query`). |",
                    "| `client_id` + `client_secret` | one auth method | Or HTTP Basic `client_id:client_secret` (recommended). |",
                    "| `client_assertion_type` + `client_assertion` | one auth method | `private_key_jwt`: an ES256/RS256 JWT, `iss`=`sub`=client ID, `aud`=this URL, expires ≤ 5 min. |",
                    "",
                    "Errors use OAuth's format: `{\"error\": \"invalid_grant\", \"error_description\": \"…\"}`.", "",
                ]
            got = ex.get((method, path))
            if got:
                status, req, res = got
                if req is not None and path not in ("/oauth/token",):
                    out += ["::: details Example request", "```json", json.dumps(req, indent=2), "```", ":::", ""]
                out += [f"**Response `{status}`**" + (" — no body" if res is None else ""), ""]
                if res is not None:
                    out += ["```json", json.dumps(res, indent=2), "```", ""]
            elif path == "/checks/nin-document":
                out += ["Returns the same shape as [`POST /checks/nin`](#post-checks-nin), plus the NIN read from the document (last 4 only).", ""]
    return "\n".join(out).rstrip() + "\n"


async def main() -> None:
    try:
        spec = app.openapi()
        ex = await record()
        OUT.write_text(render(spec, ex))
        print(f"wrote {OUT} ({len(ex)} recorded examples)")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
