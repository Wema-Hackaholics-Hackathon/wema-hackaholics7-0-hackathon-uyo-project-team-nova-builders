# Example app (Harbor)

**Harbor** is a pretend digital bank that integrates FOID the way a real customer would. It's in the repo under `demo/`. One React front end (with `@foid/react`) runs with one of two back ends:

| Command (in `demo/`) | Back end | SDK | Open |
|---|---|---|---|
| `docker compose up python --build` | FastAPI (`python/app.py`) | `foid` | `http://localhost:3100` (blue accent) |
| `docker compose up node --build` | `node:http` (`node/server.mjs`) | `@foid/node` | `http://localhost:3200` (amber accent) |

Both back ends expose the same small `/api`. Every route is one SDK call, so clicking through the UI exercises the whole SDK. The SDKs are installed from packed files in `vendor/` folders, exactly like packages from a registry. Nothing is imported from `../sdks`. You can run both at once; `docker compose down` stops them.

## Run it

**1. Start FOID** (from the repo root):

```bash
cd backend && uv run uvicorn app.main:app --reload   # :8000 — API, token endpoint, webhooks
cd frontend && pnpm dev                               # :5173 — the sign-in popup and hosted pages
cd enterprise && pnpm dev                             # :5174 — the console, to get keys
```

**2. Get keys from the console** (Test mode), and put them in `demo/.env` (`cp .env.example .env`):

| Console page | Do this | `.env` |
|---|---|---|
| API keys & webhooks | Create a test key | `FOID_API_KEY` |
| Sign-in apps | Create a test app, tick every scope. Origins are optional (test apps accept any localhost port). | `FOID_CLIENT_ID`, `FOID_CLIENT_SECRET` |
| Sign-in apps (optional) | A second app for the key pair: in Harbor, open **Setup → Generate key pair**, then paste the public JWK into that app under **Edit → Key pair** | `FOID_KEYPAIR_CLIENT_ID` |
| API keys & webhooks | Add `http://localhost:3100/webhooks/foid` | `FOID_WEBHOOK_SECRET_PYTHON` |
| API keys & webhooks | Add `http://localhost:3200/webhooks/foid` | `FOID_WEBHOOK_SECRET_NODE` |

**3. Start Harbor:** `docker compose up python --build` (or `node`). Restart it after editing `.env`. The **Setup** tab shows which values are set and can test the API key.

The containers use the host network but only listen on `127.0.0.1`, so they reach FOID on `localhost:8000`, and FOID can deliver webhooks to `localhost:3100` / `3200`. On Docker Desktop (macOS / Windows), turn on host networking in Settings → Resources → Network.

## What each tab exercises

| Tab | What you can try | SDK calls |
|---|---|---|
| **Continue with FOID** | `<ContinueWithFoid>` in every label, theme and size; `useFoidLogin()`; `signInWithFoid()` with `createPkcePair()`; the redirect fallback (block popups to see it); server-led sign-in as a popup or full-page redirect. Switch between **client secret** and **key pair**. The nonce is checked on every result. | `@foid/react`, `oauth.exchange`, `create_pkce` / `createPkce` |
| **Verifications** | Create (with **Send twice** to show the idempotency key), open the hosted page or **embed** it with `foid-verify.js`, refresh, cancel, list. | `create_verification`, `get_verification`, `request()` |
| **NIN / BVN checks** | Attested-consent checks. Untick consent to see the API refuse. | `check_nin`, `check_bvn` |
| **Subjects** | List, get, checks, trust report (needs the `financial` scope from a sign-in), delete. | `get_subject`, `request()` |
| **Webhooks** | A live list of deliveries the SDK verified. Use **Send test** in the console. **Send a forged event** must show as rejected. | `webhooks.verify` |
| **Setup** | Config status, API key test, key pair generation. | `generate_keypair` / `generateKeyPair` |

## Without Docker

```bash
cd demo/python && uv sync && uv run uvicorn app:app --port 3100   # or: cd demo/node && npm install && npm start
cd demo && npm install && DEMO_BACKEND=http://127.0.0.1:3100 npm run dev   # UI on :5300 with hot reload
```

## After changing an SDK

```bash
cd demo && ./scripts/pack-sdks.sh   # re-packs ../sdks into the vendor folders and refreshes the lockfiles
docker compose build python node
```

The full walkthrough is in `demo/README.md`.
