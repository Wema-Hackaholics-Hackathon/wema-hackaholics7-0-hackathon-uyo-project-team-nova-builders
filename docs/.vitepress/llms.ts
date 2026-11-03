// Machine-readable copies of the docs, for LLMs and AI tools.
//
//   /llms.txt          index of every page (https://llmstxt.org)
//   /llms-full.txt     every page in one file
//   /<page>.md         one page as plain markdown (e.g. /guide/quickstart.md)
//   /docs-index.json   [{ path, title, section, url, markdown }] — what the FOID MCP server searches
//
// Written into the build output by `buildEnd`, and served live by the dev server (see config.mts).
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

export interface DocPage { path: string; title: string; section: string; url: string; markdown: string }

const SKIP = new Set(['README.md'])
const SITE_SUMMARY =
  'FOID (Fintech Open Identity) lets people in Nigeria verify their identity once (NIN, BVN and a live face check) and share ' +
  'that proof with businesses only when they approve. Businesses integrate with "Continue with FOID" (OAuth 2.0 + PKCE ' +
  'sign-in), a hosted verification page, or server-to-server NIN/BVN checks, using the Python, Node and React SDKs.'

// Section order for llms.txt — the same groups as the site's navigation.
const SECTIONS: [string, RegExp][] = [
  ['Developer guides', /^\/guide\//],
  ['SDKs', /^\/sdks\//],
  ['API reference', /^\/api\//],
  ['Help for FOID users', /^\/help\//],
  ['Other', /.*/],
]

export const siteUrl = () => (process.env.DOCS_SITE_URL || 'http://localhost:5177').replace(/\/$/, '')

function walk(root: string, dir = root, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name.startsWith('.') || name === 'node_modules' || name === 'public' || name === 'scripts') continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(root, p, out)
    else if (name.endsWith('.md') && !(dir === root && SKIP.has(name))) out.push(p)
  }
  return out
}

/** "/guide/index.md" → "/guide/", "/guide/quickstart.md" → "/guide/quickstart" */
const routeOf = (file: string, root: string) => {
  const r = '/' + relative(root, file).split(sep).join('/').replace(/\.md$/, '')
  return r.endsWith('/index') ? r.slice(0, -'index'.length) : r
}
/** the .md URL for a route: "/guide/" → "/guide/index.md" */
export const mdPathOf = (route: string) => (route.endsWith('/') ? `${route}index.md` : `${route}.md`)

/** Turn VitePress markdown into plain markdown an LLM can read without the site. */
export function toPlainMarkdown(src: string, route: string): { title: string; markdown: string } {
  const site = siteUrl()
  let fm: Record<string, string> = {}
  let body = src
  const m = src.match(/^---\n([\s\S]*?)\n---\n?/)
  if (m) {
    body = src.slice(m[0].length)
    for (const line of m[1].split('\n')) {
      const kv = line.match(/^(\w+):\s*(.*)$/)
      if (kv) fm[kv[1]] = kv[2].replace(/^['"]|['"]$/g, '')
    }
  }
  if (fm.layout === 'home') {   // the landing page: describe it instead of dumping hero YAML
    body = `# FOID docs\n\n${SITE_SUMMARY}\n\nStart with the quickstart: ${site}/guide/quickstart.md\n`
  }
  body = body
    .replace(/<FoidPlayground[^>]*\/>/g, `> Interactive "Continue with FOID" playground (needs a browser): ${site}/playground`)
    .replace(/<!--[\s\S]*?-->\n?/g, '')
    .replace(/^:::\s*code-group\s*$\n?/gm, '')
    .replace(/^:::\s*(tip|warning|danger|info|details)\s*(.*)$/gm, (_s, kind: string, title: string) => `> **${title || kind[0].toUpperCase() + kind.slice(1)}**`)
    .replace(/^:::\s*$\n?/gm, '')
    .replace(/^(#{1,6} .*?)\s*\{#[\w-]+\}\s*$/gm, '$1')
    .replace(/```(\w+)\s*\[[^\]]*\]/g, '```$1')        // code-group tab labels
    // internal links → absolute .md links, so they work outside the site
    .replace(/\]\((\/[^)\s#]*)(#[^)\s]*)?\)/g, (_s, path: string, hash = '') =>
      /\.\w+$/.test(path) ? `](${site}${path}${hash})` : `](${site}${mdPathOf(path)}${hash})`)
    .replace(/\]\(\.\/([^)\s#]*)(#[^)\s]*)?\)/g, (_s, rel: string, hash = '') => {
      const base = route.endsWith('/') ? route : route.slice(0, route.lastIndexOf('/') + 1)
      return `](${site}${mdPathOf(base + rel)}${hash})`
    })
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  const title = fm.title || body.match(/^# (.+)$/m)?.[1]?.trim() || route
  return { title, markdown: body + '\n' }
}

export function collectPages(root: string, order: string[] = []): DocPage[] {
  const site = siteUrl()
  const pages = walk(root).map((file) => {
    const route = routeOf(file, root)
    const { title, markdown } = toPlainMarkdown(readFileSync(file, 'utf8'), route)
    const section = SECTIONS.find(([, re]) => re.test(route))![0]
    return { path: mdPathOf(route), title, section, url: `${site}${route}`, markdown }
  })
  const sectionRank = (p: DocPage) => SECTIONS.findIndex(([s]) => s === p.section)
  // within a section: the site's sidebar order (`order` = sidebar links), then index pages, then by path
  const navRank = (p: DocPage) => {
    const i = order.findIndex((link) => mdPathOf(link) === p.path)
    return i === -1 ? order.length : i
  }
  return pages.sort((a, b) => sectionRank(a) - sectionRank(b) || navRank(a) - navRank(b) ||
    Number(!a.path.endsWith('/index.md')) - Number(!b.path.endsWith('/index.md')) || a.path.localeCompare(b.path))
}

export function llmsTxt(pages: DocPage[]): string {
  const site = siteUrl()
  const lines = ['# FOID', '', `> ${SITE_SUMMARY}`, '',
    `Every page is also available as markdown (add .md to the URL). All pages in one file: ${site}/llms-full.txt. ` +
    `MCP server (search and read these docs from an AI tool): see ${site}/guide/ai.md.`, '']
  for (const [section] of SECTIONS) {
    const inSection = pages.filter((p) => p.section === section && p.path !== '/index.md')
    if (!inSection.length) continue
    lines.push(`## ${section}`, '')
    for (const p of inSection) {
      const first = p.markdown.split('\n').find((l) => l && !l.startsWith('#') && !l.startsWith('>') && !l.startsWith('|') && !l.startsWith('```'))
      const desc = first ? `: ${first.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[*`]/g, '').slice(0, 160)}` : ''
      lines.push(`- [${p.title}](${site}${p.path})${desc}`)
    }
    lines.push('')
  }
  return lines.join('\n')
}

export function llmsFullTxt(pages: DocPage[]): string {
  return pages.map((p) => `<page url="${p.url}" markdown="${siteUrl()}${p.path}">\n\n${p.markdown}\n</page>`).join('\n\n') + '\n'
}

export function docsIndexJson(pages: DocPage[]): string {
  return JSON.stringify({ site: siteUrl(), generated_at: new Date().toISOString(), pages }, null, 0)
}

/** Response for a dev-server request, or null if it isn't one of ours. */
export function serveLlmFile(root: string, url: string, order: string[] = []): { type: string; body: string } | null {
  const path = decodeURIComponent(url.split('?')[0])
  if (!['/llms.txt', '/llms-full.txt', '/docs-index.json'].includes(path) && !path.endsWith('.md')) return null
  const pages = collectPages(root, order)
  if (path === '/llms.txt') return { type: 'text/plain; charset=utf-8', body: llmsTxt(pages) }
  if (path === '/llms-full.txt') return { type: 'text/plain; charset=utf-8', body: llmsFullTxt(pages) }
  if (path === '/docs-index.json') return { type: 'application/json', body: docsIndexJson(pages) }
  const page = pages.find((p) => p.path === path)
  return page ? { type: 'text/markdown; charset=utf-8', body: page.markdown } : null
}

