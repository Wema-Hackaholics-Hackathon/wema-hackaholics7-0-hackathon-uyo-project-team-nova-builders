// Harbor demo — Node backend.
//
// A pretend business ("Harbor") integrating FOID with @foid/node, installed from
// vendor/foid-node-0.1.0.tgz exactly like a package from npm. It serves the React app (../dist)
// and the same /api routes as the Python backend, each one a single SDK call.
//
//   npm install && npm start        # http://127.0.0.1:3200

import { createServer } from 'node:http'
import { chmodSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Foid, FoidError, createPkce, generateKeyPair } from '@foid/node'

const HERE = dirname(fileURLToPath(import.meta.url))
const SDK_VERSION = JSON.parse(readFileSync(join(HERE, 'node_modules/@foid/node/package.json'), 'utf8')).version

// Outside Docker, read ../.env (Docker passes the same values with env_file). In the all-in-one
// docker-compose, DEMO_ENV_FILE points at the settings the backend's first-boot seed wrote.
function loadDotenv(file) {
  if (!file || !existsSync(file)) return
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const s = line.trim()
    if (!s || s.startsWith('#') || !s.includes('=')) continue
    const i = s.indexOf('=')
    process.env[s.slice(0, i).trim()] ??= s.slice(i + 1).trim()
  }
}
loadDotenv(join(HERE, '..', '.env'))
loadDotenv(process.env.DEMO_ENV_FILE)
const env = (k, d = '') => (process.env[k] || d).trim()

const API_URL = env('FOID_API_URL', 'http://localhost:8000')
const FOID_URL = env('FOID_APP_URL', 'http://localhost:5173')
const WEBHOOK_SECRET = env('FOID_WEBHOOK_SECRET') || env('FOID_WEBHOOK_SECRET_NODE')
const KEYS_DIR = env('DEMO_KEYS_DIR', resolve(HERE, '..', 'keys'))
const DIST_DIR = resolve(env('DEMO_DIST_DIR', resolve(HERE, '..', 'dist')))
const PRIVATE_KEY = join(KEYS_DIR, 'private_key.pem')
const PUBLIC_JWK = join(KEYS_DIR, 'public_jwk.json')

// One client per credential: the API key for the Open API; the client secret / key pair only
// exchange sign-in codes for their own app.
const api = new Foid({ apiKey: env('FOID_API_KEY') || undefined, baseUrl: API_URL })
const secretClient = new Foid({ clientId: env('FOID_CLIENT_ID') || undefined, clientSecret: env('FOID_CLIENT_SECRET') || undefined, baseUrl: API_URL })

// Built per exchange so a key generated from the UI works without a restart.
function keypairClient() {
  const privateKeyPem = existsSync(PRIVATE_KEY) ? readFileSync(PRIVATE_KEY, 'utf8') : undefined
  const keyId = env('FOID_KEY_ID') || (existsSync(PUBLIC_JWK) ? JSON.parse(readFileSync(PUBLIC_JWK, 'utf8')).kid : undefined)
  return new Foid({ clientId: env('FOID_KEYPAIR_CLIENT_ID') || undefined, privateKeyPem, keyId, baseUrl: API_URL })
}
const clientFor = (method) => (method === 'keypair' ? keypairClient() : secretClient)

const pending = new Map()   // server-led sign-in: state -> { verifier, nonce, method, redirectUri, at }
const events = []           // last 100 webhook deliveries

class DemoError extends Error {
  constructor(status, code, message, body) { super(message); Object.assign(this, { status, code, body }) }
}

// Run an SDK call; turn its errors into one JSON shape the UI shows.
async function sdk(fn) {
  try {
    return await fn()
  } catch (e) {
    if (e instanceof FoidError) throw new DemoError(e.status, e.code, e.description || e.message, e.body)
    if (e instanceof TypeError && /fetch/i.test(e.message)) throw new DemoError(502, 'foid_unreachable', `Can't reach FOID at ${API_URL}: ${e.cause?.code || e.message}`)
    throw new DemoError(400, 'not_configured', e.message)
  }
}

const PERSON = ['customer_ref', 'subject_id', 'first_name', 'middle_name', 'last_name', 'date_of_birth', 'email', 'phone']
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] != null && o[k] !== '' && !(Array.isArray(o[k]) && !o[k].length)).map((k) => [k, o[k]]))

const routes = [
  // ── setup ──
  ['GET', '/api/config', () => ({
    backend: 'node',
    sdk: { package: '@foid/node', version: SDK_VERSION },
    apiUrl: API_URL,
    foidUrl: FOID_URL,
    clientId: env('FOID_CLIENT_ID'),
    keypairClientId: env('FOID_KEYPAIR_CLIENT_ID'),
    has: {
      apiKey: !!env('FOID_API_KEY'),
      clientSecret: !!env('FOID_CLIENT_SECRET'),
      privateKey: existsSync(PRIVATE_KEY),
      webhookSecret: !!WEBHOOK_SECRET,
    },
  })],
  ['GET', '/api/keypair', () => ({
    exists: existsSync(PRIVATE_KEY),
    public_jwk: existsSync(PUBLIC_JWK) ? JSON.parse(readFileSync(PUBLIC_JWK, 'utf8')) : null,
  })],
  // generateKeyPair(): the private key stays in keys/, the public JWK goes to the console.
  ['POST', '/api/keypair', () => {
    if (existsSync(PRIVATE_KEY)) throw new DemoError(409, 'key_exists', 'keys/private_key.pem already exists. Delete it to make a new pair.')
    const { privateKeyPem, publicJwk } = generateKeyPair()
    mkdirSync(KEYS_DIR, { recursive: true })
    writeFileSync(PRIVATE_KEY, privateKeyPem)
    chmodSync(PRIVATE_KEY, 0o600)
    writeFileSync(PUBLIC_JWK, JSON.stringify(publicJwk, null, 2))
    return { exists: true, public_jwk: publicJwk }
  }],

  // ── Open API (API key) ──
  ['GET', '/api/ping', () => sdk(() => api.request('GET', '/ping'))],
  ['POST', '/api/verifications', ({ body }) => sdk(() => api.createVerification({
    ...pick(body, ['checks', 'scopes', 'purpose', 'return_url', 'metadata', ...PERSON]),
    idempotencyKey: body.idempotency_key || undefined,
  }))],
  ['GET', '/api/verifications', ({ query }) => {
    const params = pick(Object.fromEntries(query), ['status', 'customer_ref'])
    return sdk(() => api.request('GET', '/verifications', Object.keys(params).length ? { params } : {}))
  }],
  ['GET', /^\/api\/verifications\/([\w-]+)$/, ({ m }) => sdk(() => api.getVerification(m[1]))],
  ['POST', /^\/api\/verifications\/([\w-]+)\/cancel$/, ({ m }) => sdk(() => api.request('POST', `/verifications/${m[1]}/cancel`))],
  ['POST', /^\/api\/checks\/(nin|bvn)$/, ({ m, body }) => {
    const payload = {
      number: body.number || '',
      consent: { obtained: !!body.consent_obtained, purpose: body.purpose || 'Account opening' },
      ...pick(body, PERSON),
    }
    return sdk(() => (m[1] === 'nin' ? api.checkNin(payload) : api.checkBvn(payload)))
  }],
  ['GET', '/api/subjects', ({ query }) => {
    const ref = query.get('customer_ref')
    return sdk(() => api.request('GET', '/subjects', ref ? { params: { customer_ref: ref } } : {}))
  }],
  ['GET', /^\/api\/subjects\/([\w-]+)$/, ({ m }) => sdk(() => api.getSubject(m[1]))],
  ['GET', /^\/api\/subjects\/([\w-]+)\/checks$/, ({ m }) => sdk(() => api.request('GET', `/subjects/${m[1]}/checks`))],
  ['GET', /^\/api\/subjects\/([\w-]+)\/trust-report$/, ({ m }) => sdk(() => api.request('GET', `/subjects/${m[1]}/trust-report`))],
  ['DELETE', /^\/api\/subjects\/([\w-]+)$/, async ({ m }) => {
    await sdk(() => api.request('DELETE', `/subjects/${m[1]}`))
    return { deleted: m[1] }
  }],

  // ── Continue with FOID ──
  // Server-led sign-in: createPkce() here, keep the verifier + nonce, hand the browser a URL.
  ['POST', '/api/signin/start', ({ body }) => {
    const method = body.method === 'keypair' ? 'keypair' : 'secret'
    const clientId = method === 'keypair' ? env('FOID_KEYPAIR_CLIENT_ID') : env('FOID_CLIENT_ID')
    if (!clientId) throw new DemoError(400, 'not_configured', `Set ${method === 'keypair' ? 'FOID_KEYPAIR_CLIENT_ID' : 'FOID_CLIENT_ID'} in .env`)
    const p = createPkce()
    const q = new URLSearchParams({
      client_id: clientId, scope: body.scope || 'profile', state: p.state, nonce: p.nonce,
      code_challenge: p.codeChallenge, code_challenge_method: 'S256',
    })
    const redirectUri = body.redirect_uri || null
    if (redirectUri) { q.set('response_mode', 'query'); q.set('redirect_uri', redirectUri) }
    else { q.set('response_mode', 'web_message'); q.set('origin', body.origin || '') }
    pending.set(p.state, { verifier: p.codeVerifier, nonce: p.nonce, method, redirectUri, at: Date.now() })
    for (const [s, v] of pending) if (Date.now() - v.at > 600_000) pending.delete(s)
    return { authorize_url: `${FOID_URL.replace(/\/$/, '')}/oauth/authorize?${q}`, state: p.state }
  }],
  // foid.oauth.exchange(code, codeVerifier): the one-time code -> who signed in and what they shared.
  ['POST', '/api/signin/exchange', async ({ body }) => {
    const started = !body.code_verifier && body.state ? pending.get(body.state) : null
    if (started) pending.delete(body.state)
    const { method, verifier, redirectUri, nonce } = started
      ? started
      : { method: body.method || 'secret', verifier: body.code_verifier, redirectUri: body.redirect_uri, nonce: body.nonce }
    if (!verifier) throw new DemoError(400, 'missing_verifier', 'No code_verifier for this sign-in (or the server-led state expired)')
    const result = await sdk(() => clientFor(method).oauth.exchange(body.code || '', verifier, redirectUri ? { redirectUri } : {}))
    return {
      backend: 'node', auth: method === 'keypair' ? 'private_key_jwt' : 'client_secret',
      server_led: !!started, nonce_ok: nonce ? result.nonce === nonce : null, result,
    }
  }],

  // ── webhooks ──
  ['GET', '/api/webhooks', () => ({ secret_configured: !!WEBHOOK_SECRET, events })],
  ['DELETE', '/api/webhooks', () => { events.length = 0; return { cleared: true } }],
]

// ── HTTP plumbing ─────────────────────────────────────────────────────────────
function send(res, status, data, type = 'application/json') {
  res.writeHead(status, { 'Content-Type': type })
  res.end(type === 'application/json' ? JSON.stringify(data) : data)
}

const readRaw = (req) => new Promise((ok, fail) => {
  const chunks = []
  req.on('data', (c) => chunks.push(c)).on('end', () => ok(Buffer.concat(chunks))).on('error', fail)
})

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json' }

function serveApp(res, pathname) {
  const file = resolve(DIST_DIR, '.' + pathname)
  const inside = file.startsWith(DIST_DIR + sep)
  const target = inside && existsSync(file) && statSync(file).isFile() ? file : join(DIST_DIR, 'index.html')
  if (!existsSync(target)) return send(res, 200, { message: 'API is up. Build the UI (npm run build) or use npm run dev.' })
  send(res, 200, readFileSync(target), TYPES[extname(target)] || 'application/octet-stream')
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const path = url.pathname

  // The webhook needs the RAW body for the signature check.
  if (req.method === 'POST' && path === '/webhooks/foid') {
    const raw = await readRaw(req)
    if (!WEBHOOK_SECRET) {
      events.unshift({ verified: false, error: 'FOID_WEBHOOK_SECRET is not set', at: Date.now() / 1000 })
      return send(res, 500, { error: 'webhook secret not configured' })
    }
    try {
      const event = api.webhooks.verify(raw, req.headers['foid-signature'] || '', WEBHOOK_SECRET)
      events.unshift({ verified: true, at: Date.now() / 1000, event })
      events.length = Math.min(events.length, 100)
      return send(res, 200, { received: true })
    } catch (e) {
      events.unshift({ verified: false, error: e.message, at: Date.now() / 1000 })
      return send(res, 400, { error: e.message })
    }
  }

  if (!path.startsWith('/api/')) return serveApp(res, path)

  for (const [method, pattern, handler] of routes) {
    if (method !== req.method) continue
    const m = typeof pattern === 'string' ? (pattern === path ? [path] : null) : path.match(pattern)
    if (!m) continue
    try {
      let body = {}
      if (req.method === 'POST') {
        const raw = await readRaw(req)
        try { body = raw.length ? JSON.parse(raw) : {} } catch { throw new DemoError(400, 'bad_json', 'Body must be JSON') }
      }
      return send(res, 200, await handler({ m, body, query: url.searchParams }))
    } catch (e) {
      const err = e instanceof DemoError ? e : new DemoError(500, 'server_error', e.message)
      return send(res, err.status || 500, { error: { status: err.status, code: err.code, message: err.message, body: err.body ?? null } })
    }
  }
  send(res, 404, { error: { status: 404, code: 'not_found', message: `No route ${req.method} ${path}` } })
})

const HOST = env('HOST', '127.0.0.1')
const PORT = Number(env('PORT', '3200'))
server.listen(PORT, HOST, () => {
  console.log(`Harbor demo (Node, @foid/node ${SDK_VERSION}) → http://localhost:${PORT}`)
  console.log(`  FOID API ${API_URL} · sign-in popup ${FOID_URL}`)
})
