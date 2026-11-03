"""Local/demo seed: a ready-to-use test business + FOID user, for the all-in-one docker-compose.

    python -m app.dev_seed --out /data/demo.env

Runs once (skips when --out already exists). Goes through the real API routes in-process, so everything
is created exactly as the console would create it:

- console account  demo@harbor.example / HarborDemo#2026   (business "Harbor (demo)", email verified)
- a TEST API key, a TEST "Continue with FOID" app (client secret), TEST webhooks to the demo containers
- FOID user        ada@example.com / FoidTester#2026   (email verified; verify NIN/BVN/face in the app)

Writes the demo's server-side settings (API key, client ID/secret, webhook secrets) to --out, which the
demo containers read. Test mode only: nothing here can touch live data. Never run this in production.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlmodel import select

CONSOLE_EMAIL, CONSOLE_PASSWORD = "demo@harbor.example", "HarborDemo#2026"
USER_EMAIL, USER_PASSWORD = "ada@example.com", "FoidTester#2026"
SCOPES = ["profile", "identity", "contact", "liveness", "financial"]


async def seed(out: Path, demo_hosts: dict[str, int]) -> None:
    from app.config import _get_engine, _get_session_factory, get_settings, init_db
    from app.core.schema_check import check_schema, has_table
    from app.main import app
    from app.models import Credential, User
    from app.utils.limiter import limiter

    if get_settings().ENV == "production":
        sys.exit("dev_seed refuses to run with ENV=production")
    limiter.enabled = False
    # Same as app startup: a brand-new database gets every table and is stamped at the Alembic head;
    # an existing one is only checked (migrations are Alembic's job).
    engine = _get_engine()
    was_empty = not await has_table(engine, "users")
    if was_empty:
        await init_db()
    schema = await check_schema(engine, was_empty=was_empty)
    if not schema.ok:
        sys.exit(f"dev_seed: {schema.message}")

    async def sql(stmt: str, **params: Any) -> None:
        async with _get_session_factory()() as db:
            await db.exec(text(stmt).bindparams(**params))
            await db.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://seed") as c:
        def ok(r: httpx.Response) -> Any:
            if r.status_code >= 400:
                sys.exit(f"seed failed: {r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:300]}")
            return r.json() if r.content else None

        r = await c.post("/api/v1/console/auth/signup", json={"first_name": "Harbor", "last_name": "Developer",
                         "email": CONSOLE_EMAIL, "password": CONSOLE_PASSWORD, "company_name": "Harbor (demo)"})
        if r.status_code == 409:
            r = await c.post("/api/v1/console/auth/login", json={"email": CONSOLE_EMAIL, "password": CONSOLE_PASSWORD})
        h = {"Authorization": f"Bearer {ok(r)['access_token']}"}
        await sql("UPDATE console_users SET email_verified_at = created_at WHERE email = :e AND email_verified_at IS NULL",
                  e=CONSOLE_EMAIL)
        org = ok(await c.get("/api/v1/business/organisations", headers=h))[0]["id"]
        base = f"/api/v1/business/organisations/{org}"

        key = ok(await c.post(f"{base}/api-keys", headers=h, json={"env": "test", "name": "Harbor demo"}))
        redirects = [f"http://localhost:{port}/callback" for port in demo_hosts.values()]
        app_ = ok(await c.post(f"{base}/apps", headers=h, json={
            "env": "test", "name": "Harbor web", "scopes": SCOPES, "redirect_uris": redirects}))
        hooks = {name: ok(await c.post(f"{base}/webhooks", headers=h, json={
            "env": "test", "url": f"http://{host}:{port}/webhooks/foid"}))
            for name, (host, port) in {"PYTHON": ("demo-python", demo_hosts["python"]),
                                       "NODE": ("demo-node", demo_hosts["node"])}.items()}

        r = await c.post("/api/v1/auth/signup", json={"first_name": "Ada", "last_name": "Obi", "nin": "70000000001",
                         "email": USER_EMAIL, "password": USER_PASSWORD})
        if r.status_code not in (201, 409):
            ok(r)
    async with _get_session_factory()() as db:          # mark the test person's email as verified
        user = (await db.exec(select(User).where(User.email == USER_EMAIL))).first()
        cred = (await db.exec(select(Credential).where(Credential.user_id == user.id))).first() if user else None
        if cred is not None:
            cred.claims = {**cred.claims, "email_verified": True}  # type: ignore[assignment]
            db.add(cred)
            await db.commit()

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join([
        "# Written by app.dev_seed for the demo containers. Test-mode credentials only.",
        f"FOID_API_KEY={key['secret']}",
        f"FOID_CLIENT_ID={app_['client_id']}",
        f"FOID_CLIENT_SECRET={app_['client_secret']}",
        f"FOID_WEBHOOK_SECRET_PYTHON={hooks['PYTHON']['secret']}",
        f"FOID_WEBHOOK_SECRET_NODE={hooks['NODE']['secret']}",
        "",
    ]))
    print(f"""
┌──────────────────────────────────────────────────────────────────────┐
│ FOID demo data is ready (test mode)                                  │
│   Business console  http://localhost:5174                            │
│     {CONSOLE_EMAIL:<24} {CONSOLE_PASSWORD:<38}  │
│   FOID user app     http://localhost:5173                            │
│     {USER_EMAIL:<24} {USER_PASSWORD:<38}  │
│   Harbor demo       http://localhost:3100 (Python) · :3200 (Node)    │
│   Docs              http://localhost:5177                            │
│   Emails (sign-in codes) are printed in these backend logs.          │
└──────────────────────────────────────────────────────────────────────┘
""", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Seed a test business + FOID user for local demos")
    p.add_argument("--out", type=Path, required=True, help="where to write the demo containers' settings")
    p.add_argument("--python-port", type=int, default=3100)
    p.add_argument("--node-port", type=int, default=3200)
    a = p.parse_args()
    if a.out.exists() and "FOID_API_KEY=" in a.out.read_text():
        print(f"dev_seed: {a.out} exists — demo data already seeded (delete the volume to start over)", flush=True)
        return
    asyncio.run(seed(a.out, {"python": a.python_port, "node": a.node_port}))


if __name__ == "__main__":
    main()
