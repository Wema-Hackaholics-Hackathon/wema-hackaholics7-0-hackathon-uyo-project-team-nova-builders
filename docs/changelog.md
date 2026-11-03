# Changelog

Changes to the FOID API, SDKs and docs. Dates are when the change shipped.

## 2026-11-03

**Continue with FOID**
- Sign-in apps in the console (Sign-in apps page): client ID, client secrets (shown once, hashed, 24-hour overlap when rotated) and key pairs (`private_key_jwt`).
- Popup sign-in with email code, consent screen, fresh face check per new business (live), and **Save to FOID** for people without an account.
- Token endpoint `POST /api/open/v1/oauth/token` — PKCE required, codes single use and valid 60 seconds; a replayed code revokes the grant.

**SDKs (0.1.0)**
- `foid` (Python), `@foid/node`, `@foid/react` — code exchange, key pairs, webhook verification, Open API helpers, the button and hook.
- The button now uses the FOID mark.

**Webhooks**
- Webhook URLs are checked when saved and at every delivery: https only in live, no private or internal addresses, no redirects, localhost only for test endpoints. See [Webhooks](/guide/webhooks#allowed-urls).

**AI tools**
- `llms.txt`, `llms-full.txt` and a markdown copy of every page; a **Copy page** menu (copy, or open in ChatGPT / Claude / Perplexity).
- A read-only MCP server at `/mcp` that searches and reads these docs. See [Use FOID docs with AI](/guide/ai).

**Docs**
- This site, with a live [playground](/playground) and an [API reference](/api/reference) generated from the backend.
