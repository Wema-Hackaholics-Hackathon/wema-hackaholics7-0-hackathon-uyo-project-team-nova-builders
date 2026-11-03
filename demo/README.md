# Harbor — FOID SDK demo

Harbor is a pretend digital bank that integrates FOID. It uses the SDKs the way a customer would: they're installed from packaged files, not imported from `../sdks`. Each Docker image contains the React app plus one backend:

| Command | Backend | SDK installed | Open |
|---|---|---|---|
| `docker compose up python --build` | FastAPI (`python/app.py`) | `foid` from `python/vendor/*.whl` | http://localhost:3100 (blue) |
| `docker compose up node --build` | `node:http` (`node/server.mjs`) | `@foid/node` from `node/vendor/*.tgz` | http://localhost:3200 (amber) |

Both images also install the React app's `@foid/react` from `vendor/*.tgz`. The accent colour tells you which backend you're on. You can run both at the same time. Stop them with `docker compose down`.

```
demo/
├── docker-compose.yml     services: python, node (host network, bound to 127.0.0.1)
├── .env.example           copy to .env, then fill in from the FOID console
├── keys/                  key pair for private_key_jwt (git-ignored, shared by both backends)
├── vendor/                @foid/react tarball
├── src/                   React app (Vite)
├── python/                Dockerfile, app.py, pyproject + uv.lock, vendor/ (foid wheel)
├── node/                  Dockerfile, server.mjs, package.json, vendor/ (@foid/node tarball)
└── scripts/pack-sdks.sh   re-pack ../sdks into the vendor folders after changing an SDK
```

## 1. Run FOID

The demo talks to FOID on your machine:

```bash
cd backend && uv run uvicorn app.main:app --reload   # :8000 — API, token endpoint, webhooks
cd frontend && pnpm dev                               # :5173 — sign-in popup, hosted verification
```

## 2. Get the keys from the console (test environment)

```bash
cp .env.example .env
```

| Console page | Do this | Put in `.env` |
|---|---|---|
| API keys | Create a **test** key | `FOID_API_KEY` |
| Sign-in apps | Create a **test** app and tick every scope. Origins are optional: test apps accept any `http://localhost` port. Add redirect URIs `http://localhost:3100/callback` and `http://localhost:3200/callback` | `FOID_CLIENT_ID`, `FOID_CLIENT_SECRET` |
| Sign-in apps (optional) | Create a second test app for the key pair. Start the demo, open **Setup → Generate key pair**, then paste the public JWK into that app under Edit → Key pair | `FOID_KEYPAIR_CLIENT_ID` |
| Webhooks | Add `http://localhost:3100/webhooks/foid` (all events) | `FOID_WEBHOOK_SECRET_PYTHON` |
| Webhooks | Add `http://localhost:3200/webhooks/foid` (all events) | `FOID_WEBHOOK_SECRET_NODE` |

After editing `.env`, restart the container (`docker compose up python` again). The **Setup** tab shows what's set and has a button that checks the API key.

## 3. What to try

| Tab | Covers | SDK calls |
|---|---|---|
| Continue with FOID | `<ContinueWithFoid>` (every label, theme and size), `useFoidLogin()`, `signInWithFoid()` + `createPkcePair()`, the redirect fallback via `redirectUri` + `handleRedirectCallback()` (block popups to see it), and server-led PKCE as a popup or a full-page redirect. Switch between **client secret** and **key pair**. The nonce is checked on every result. | React SDK; `oauth.exchange`, `create_pkce` / `createPkce` |
| Verifications | Create, with **Send twice** to test the Idempotency-Key. Open the hosted page or **embed** it with `foid-verify.js`, then refresh, cancel and list. | `create_verification`, `get_verification`, `request()` |
| NIN / BVN checks | Attested-consent checks. Untick consent to see the API refuse. | `check_nin`, `check_bvn` |
| Subjects | List, get, checks, trust report (needs the `financial` scope from a sign-in) and delete. | `get_subject`, `request()` |
| Webhooks | Live list of deliveries checked by the SDK. Use console → Webhooks → **Send test event**. **Send a forged event** must show as rejected. | `webhooks.verify` |
| Setup | Config status, the API key check, and key pair generation. | `generate_keypair` / `generateKeyPair` |

In test mode every check passes with sandbox data. Continue with FOID is the exception: it signs in a real FOID user and shares only their real first and last name.

## Without Docker

```bash
cd python && uv sync && uv run uvicorn app:app --port 3100   # or: cd node && npm install && npm start
npm install && DEMO_BACKEND=http://127.0.0.1:3100 npm run dev   # UI on :5300 with hot reload
```

Run `npm run build` first if you want the backend itself to serve the UI. It reads `demo/dist`.

## After changing an SDK

```bash
./scripts/pack-sdks.sh            # re-packs ../sdks into the vendor folders and refreshes the lockfiles
docker compose build python node
```

## Notes

- The servers bind `127.0.0.1` on the host network. That lets the containers reach FOID on `localhost:8000` and lets FOID deliver webhooks to `localhost:3100` and `localhost:3200`. Nothing is exposed to your network. Docker Desktop on macOS or Windows needs host networking turned on (Settings → Resources → Network).
- `.env` and `keys/` are git-ignored. The browser only receives the two public client IDs.
- The SDKs have no helper for `POST /checks/nin-document` (multipart upload), so the demo doesn't cover it.
