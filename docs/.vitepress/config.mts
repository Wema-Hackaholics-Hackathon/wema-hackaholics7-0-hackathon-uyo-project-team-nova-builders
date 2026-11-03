import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitepress'
import { collectPages, docsIndexJson, llmsFullTxt, llmsTxt, serveLlmFile } from './llms'

const DOCS_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

// FOID docs. `pnpm dev` → http://localhost:5177
// The playground calls the FOID backend. In dev, /api is proxied to FOID_API_URL (default :8000);
// for a static deploy set VITE_FOID_API_URL at build time and add the docs origin to the
// backend's ALLOWED_ORIGINS.
const api = process.env.FOID_API_URL || 'http://localhost:8000'

const developers = [
  {
    text: 'Start here',
    items: [
      { text: 'Introduction', link: '/guide/' },
      { text: 'Quickstart', link: '/guide/quickstart' },
      { text: 'Core concepts', link: '/guide/concepts' },
      { text: 'Test and live mode', link: '/guide/test-and-live' },
    ],
  },
  {
    text: 'Integrate',
    items: [
      { text: 'Continue with FOID', link: '/guide/continue-with-foid' },
      { text: 'Hosted verification', link: '/guide/hosted-verification' },
      { text: 'NIN and BVN checks', link: '/guide/checks' },
      { text: 'Subjects and consent', link: '/guide/subjects' },
      { text: 'Webhooks', link: '/guide/webhooks' },
    ],
  },
  {
    text: 'Production',
    items: [
      { text: 'Going live', link: '/guide/going-live' },
      { text: 'Security checklist', link: '/guide/security' },
      { text: 'Errors, limits, idempotency', link: '/guide/errors' },
    ],
  },
  {
    text: 'AI tools',
    items: [{ text: 'Use FOID docs with AI', link: '/guide/ai' }],
  },
]

const sdks = [
  {
    text: 'SDKs',
    items: [
      { text: 'Overview', link: '/sdks/' },
      { text: 'Python — foid', link: '/sdks/python' },
      { text: 'Node — @foid/node', link: '/sdks/node' },
      { text: 'React — @foid/react', link: '/sdks/react' },
      { text: 'Example app (Harbor)', link: '/sdks/example-app' },
    ],
  },
  { text: 'Try it', items: [{ text: 'Playground', link: '/playground' }] },
]

const apiRef = [
  {
    text: 'API reference',
    items: [
      { text: 'Overview', link: '/api/' },
      { text: 'Endpoints', link: '/api/reference' },
    ],
  },
]

const help = [
  {
    text: 'Using FOID',
    items: [
      { text: 'Help centre', link: '/help/' },
      { text: 'Create your FOID', link: '/help/getting-started' },
      { text: 'Verify your identity', link: '/help/verify-identity' },
      { text: 'Your FOID code', link: '/help/foid-code' },
      { text: 'Continue with FOID', link: '/help/continue-with-foid' },
      { text: 'Connected apps and consent', link: '/help/connected-apps' },
      { text: 'Keep your account safe', link: '/help/security' },
      { text: 'FAQ', link: '/help/faq' },
    ],
  },
]

// Sidebar order, reused for llms.txt / llms-full.txt
const NAV_ORDER = [...developers, ...sdks, ...apiRef, ...help].flatMap((g) => g.items.map((i) => i.link))

export default defineConfig({
  title: 'FOID Docs',
  description: 'Verify once, share with consent — FOID developer docs, SDKs and help.',
  lang: 'en-NG',
  cleanUrls: true,
  srcExclude: ['README.md'],   // repo README for the docs project, not a site page
  lastUpdated: existsSync(join(DOCS_ROOT, '..', '.git')),   // needs git history (off in Docker builds)
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['meta', { name: 'theme-color', content: '#C800DE' }],
  ],
  themeConfig: {
    logo: '/foid-mark.svg',
    siteTitle: 'FOID Docs',
    nav: [
      { text: 'Developers', link: '/guide/', activeMatch: '/guide/' },
      { text: 'SDKs', link: '/sdks/', activeMatch: '/sdks/' },
      { text: 'Playground', link: '/playground' },
      { text: 'API', link: '/api/', activeMatch: '/api/' },
      { text: 'Help', link: '/help/', activeMatch: '/help/' },
      { text: 'Changelog', link: '/changelog' },
    ],
    sidebar: {
      '/guide/': developers,
      '/sdks/': sdks,
      '/playground': sdks,
      '/api/': apiRef,
      '/help/': help,
    },
    search: { provider: 'local' },
    outline: { level: [2, 3] },
    footer: {
      message: 'FOID — Fintech Open Identity. Test mode never touches real identity data.',
    },
  },
  // llms.txt, llms-full.txt, docs-index.json and a .md copy of every page (see llms.ts)
  buildEnd(site) {
    const pages = collectPages(DOCS_ROOT, NAV_ORDER)
    const write = (path: string, body: string) => {
      const file = join(site.outDir, path)
      mkdirSync(dirname(file), { recursive: true })
      writeFileSync(file, body)
    }
    write('llms.txt', llmsTxt(pages))
    write('llms-full.txt', llmsFullTxt(pages))
    write('docs-index.json', docsIndexJson(pages))
    for (const p of pages) write(p.path, p.markdown)
  },
  vite: {
    plugins: [{
      name: 'foid-llm-files',   // the same files, live, in `pnpm dev`
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // VitePress itself imports pages as /path.md modules — leave those (and HMR) alone.
          const isModule = req.headers['sec-fetch-dest'] === 'script' || /[?&](import|t=|v=)/.test(req.url || '')
          const hit = req.url && !isModule ? serveLlmFile(DOCS_ROOT, req.url, NAV_ORDER) : null
          if (!hit) return next()
          res.setHeader('Content-Type', hit.type)
          res.setHeader('Access-Control-Allow-Origin', '*')
          res.end(hit.body)
        })
      },
    }],
    server: { proxy: { '/api': { target: api, changeOrigin: true } } },
    // @foid/react comes from ../sdks/react; make it use this site's single React copy.
    resolve: { dedupe: ['react', 'react-dom'] },
    ssr: { noExternal: ['@foid/react'] },
  },
})
