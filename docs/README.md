# FOID docs site

The FOID documentation: developer guides, SDK docs, the API reference, a live "Continue with FOID" playground and the help centre for FOID users. Built with [VitePress](https://vitepress.dev).

```
docs/
├── index.md              home page
├── guide/                developer guides (quickstart, Continue with FOID, webhooks, …)
├── sdks/                 Python, Node and React SDK pages + the Harbor example app
├── api/                  API overview + reference.md (GENERATED — don't edit by hand)
├── help/                 help centre for people using the FOID app
├── playground.md         the live Continue with FOID button
├── changelog.md
├── scripts/gen_api_reference.py   generates api/reference.md from the backend
└── .vitepress/           config (nav, sidebar), theme, playground component
```

## Run it

```bash
cd docs
pnpm install
pnpm dev              # http://localhost:5177
```

Most pages work on their own. **The playground** also needs FOID running:

| Server | Command | Why |
|---|---|---|
| Backend :8000 | `cd backend && uv run uvicorn app.main:app --reload` | The dev server proxies `/api` to it; it creates the built-in docs test app on first use |
| User app :5173 | `cd frontend && pnpm dev` | Hosts the FOID sign-in popup |

To point the dev proxy at a different backend: `FOID_API_URL=http://localhost:8001 pnpm dev`.

## Regenerate the API reference

`api/reference.md` is generated from the backend — the endpoint list, request fields and **real example responses** (recorded against a throwaway in-memory database, no network):

```bash
cd docs
pnpm api              # = cd ../backend && uv run python ../docs/scripts/gen_api_reference.py
```

Run it whenever an Open API endpoint changes.

## Build and deploy

```bash
pnpm build            # static site in .vitepress/dist
pnpm preview          # serve the build on :5177
```

Deploying the static site:

1. Build with **`VITE_FOID_API_URL`** set to the public backend URL (e.g. `VITE_FOID_API_URL=https://foid-iy7u.onrender.com pnpm build`). Without it the playground calls `/api` on the docs host, which only works if that host proxies `/api` to the backend.
2. On the backend, add the docs origin to **`ALLOWED_ORIGINS`** (CORS) and set **`DOCS_SITE_URL`** to it — the built-in docs test app only accepts sign-ins started from that origin.
3. Set **`VITE_DOCS_URL`** in the user app and console builds so their *Docs* / *Help* links point to the deployed site.
4. To turn the playground off on a server: `DOCS_PLAYGROUND=false` on the backend.
5. Build with **`DOCS_SITE_URL`** set to the public docs URL (e.g. `DOCS_SITE_URL=https://docs-foid.pages.dev pnpm build`) so the links inside `llms.txt`, `llms-full.txt` and the `.md` copies are absolute and reachable.

### Where FOID is deployed

| What | URL | Build / runtime settings |
|---|---|---|
| Backend (Render) | https://foid-iy7u.onrender.com | `DOCS_SITE_URL=https://docs-foid.pages.dev`, `PUBLIC_APP_URL=https://usefoid.pages.dev`, `CONSOLE_URL=https://admin-foid.pages.dev`, the three sites in `ALLOWED_ORIGINS` |
| Docs (Cloudflare Pages) | https://docs-foid.pages.dev | `VITE_FOID_API_URL=https://foid-iy7u.onrender.com`, `DOCS_SITE_URL=https://docs-foid.pages.dev` |
| FOID user app | https://usefoid.pages.dev | `VITE_DOCS_URL=https://docs-foid.pages.dev` |
| Business console | https://admin-foid.pages.dev | `VITE_DOCS_URL=https://docs-foid.pages.dev` |

### For AI tools

Every build (and `pnpm dev`) also produces machine-readable copies of the docs — see `.vitepress/llms.ts`:

| File | What it is |
|---|---|
| `/llms.txt` | index of every page ([llms.txt](https://llmstxt.org)) |
| `/llms-full.txt` | every page in one file |
| `/<page>.md` | one page as plain markdown |
| `/docs-index.json` | all pages as JSON — what the backend's MCP server (`POST /mcp`, `DOCS_MCP`) searches |

Each page also has a **Copy page** menu (copy as markdown, open in ChatGPT / Claude / Perplexity) — `.vitepress/theme/PageActions.vue`. User-facing guide: `guide/ai.md`.

See [`.env.example`](./.env.example) for the variables.
