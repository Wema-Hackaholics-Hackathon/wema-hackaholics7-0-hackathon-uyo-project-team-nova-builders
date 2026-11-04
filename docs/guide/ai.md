# Use FOID docs with AI

Building with an AI assistant? Give it the FOID docs, so it writes code against the real SDKs and API instead of guessing.

There are three ways to do it:

| | Best for | Setup |
|---|---|---|
| [Copy page / Open in…](#copy-a-page) | A quick question about one page | None — the menu at the top of every page |
| [`llms.txt`](#llms-txt) | Pasting all the docs into a chat or a prompt | None — a URL |
| [MCP server](#mcp-server) | Your editor or agent searching the docs while it works | One command |

## Copy a page

Every page has a **Copy page** button at the top right. Its menu has:

- **Copy page** — the page as clean markdown (code samples included), ready to paste into any AI tool.
- **View as Markdown** — the same text in your browser. Every page has one: add `.md` to the URL, e.g. <a href="/guide/quickstart.md" target="_blank"><code>/guide/quickstart.md</code></a>.
- **Open in ChatGPT / Claude / Perplexity** — opens a new chat that reads this page. When you run the docs on your own machine (`localhost`), those services can't reach it, so the page is copied to your clipboard and the chat asks you to paste it.

## llms.txt

The docs follow the [llms.txt](https://llmstxt.org) convention:

| URL | What it is |
|---|---|
| <a href="/llms.txt" target="_blank"><code>/llms.txt</code></a> | An index: every page with a one-line summary and a link to its markdown |
| <a href="/llms-full.txt" target="_blank"><code>/llms-full.txt</code></a> | Every page in one file — paste it into a chat or a system prompt |
| `/<page>.md` | One page as markdown |

All three are generated from the same pages you're reading, every time the docs are built, so they never drift.

## MCP server

FOID runs a [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI tools search and read these docs on their own. It's read-only, needs no key, and only serves the public docs — nothing about any person or business.

| | |
|---|---|
| URL | `https://foid-iy7u.onrender.com/mcp` |
| Running FOID locally | `http://localhost:8000/mcp` (the backend; it reads the docs from the docs site, so run `pnpm dev` in `docs/` too) |
| Transport | Streamable HTTP |

**Tools**

| Tool | What it does |
|---|---|
| `search_foid_docs` | `query`, optional `limit` (1–10) → the best-matching sections, each with an excerpt and a link |
| `read_foid_doc` | `path` (e.g. `/guide/continue-with-foid`) → that page as markdown |
| `list_foid_docs` | Every page, grouped by section |

### Add it to your tool

::: code-group

```bash [Claude Code]
claude mcp add --transport http foid-docs https://foid-iy7u.onrender.com/mcp
```

```json [Cursor — .cursor/mcp.json]
{
  "mcpServers": {
    "foid-docs": { "url": "https://foid-iy7u.onrender.com/mcp" }
  }
}
```

```json [VS Code — .vscode/mcp.json]
{
  "servers": {
    "foid-docs": { "type": "http", "url": "https://foid-iy7u.onrender.com/mcp" }
  }
}
```

```json [Windsurf — mcp_config.json]
{
  "mcpServers": {
    "foid-docs": { "serverUrl": "https://foid-iy7u.onrender.com/mcp" }
  }
}
```

```json [Other clients (stdio only)]
{
  "mcpServers": {
    "foid-docs": { "command": "npx", "args": ["-y", "mcp-remote", "https://foid-iy7u.onrender.com/mcp"] }
  }
}
```

:::

- **Claude (desktop and claude.ai):** Settings → Connectors → **Add custom connector**, name it *FOID Docs*, URL `https://foid-iy7u.onrender.com/mcp`.
- **ChatGPT:** Settings → Apps & Connectors → Advanced settings → turn on **Developer mode**, then **Create** a connector with the URL `https://foid-iy7u.onrender.com/mcp` and no authentication.

Claude and ChatGPT connect from their own servers, so they need the public `https://` URL. Editor tools like Claude Code, Cursor and VS Code run on your machine and can use `http://localhost:8000/mcp`.

Then just ask, for example: *"Using the FOID docs, add Continue with FOID to my Next.js app with a Node backend."*

### Check it's working

```bash
curl -s https://foid-iy7u.onrender.com/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_foid_docs","arguments":{"query":"verify webhook signature"}}}'
```

You should get back sections from the [Webhooks](/guide/webhooks) guide.

::: tip Running FOID yourself
The MCP server is part of the backend: `POST /mcp`. It loads the docs from `DOCS_SITE_URL/docs-index.json` and caches them for 10 minutes. Turn it off with `DOCS_MCP=false`.
:::
