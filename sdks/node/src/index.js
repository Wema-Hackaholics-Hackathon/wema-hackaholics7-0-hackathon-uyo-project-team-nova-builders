// FOID server SDK for Node 18+ (no dependencies). Server-side only — never ship secrets to a browser.
import { createHash, createHmac, createPrivateKey, generateKeyPairSync, randomBytes, sign, timingSafeEqual } from 'node:crypto'

export const DEFAULT_BASE_URL = 'https://api.foid.ng'
const ASSERTION_TYPE = 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer'
const b64url = (buf) => Buffer.from(buf).toString('base64url')

export class FoidError extends Error {
  constructor(status, code, message, body) {
    super(`${status} ${code}: ${message}`)
    Object.assign(this, { status, code, body })
    this.description = message
  }
}

async function toError(res) {
  let body
  try { body = await res.json() } catch { return new FoidError(res.status, 'http_error', res.statusText) }
  if (typeof body.error === 'string') return new FoidError(res.status, body.error, body.error_description ?? '', body)
  const e = body.error ?? {}
  return new FoidError(res.status, e.code ?? 'http_error', e.message ?? JSON.stringify(body), body)
}

/** { codeVerifier, codeChallenge, state, nonce } — for servers that start the sign-in themselves. */
export function createPkce() {
  const codeVerifier = b64url(randomBytes(48))
  return {
    codeVerifier,
    codeChallenge: b64url(createHash('sha256').update(codeVerifier).digest()),
    state: b64url(randomBytes(16)),
    nonce: b64url(randomBytes(16)),
  }
}

/** { privateKeyPem (keep secret), publicJwk (paste in FOID Console → Sign-in apps) } for private_key_jwt. */
export function generateKeyPair() {
  const { privateKey, publicKey } = generateKeyPairSync('ec', { namedCurve: 'P-256' })
  const jwk = publicKey.export({ format: 'jwk' })
  return {
    privateKeyPem: privateKey.export({ type: 'pkcs8', format: 'pem' }),
    publicJwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y, alg: 'ES256', kid: randomBytes(4).toString('hex') },
  }
}

/** 60-second ES256 JWT proving the request comes from the private-key holder. */
export function clientAssertion(privateKeyPem, clientId, audience, kid) {
  const now = Math.floor(Date.now() / 1000)
  const header = { alg: 'ES256', typ: 'JWT', ...(kid ? { kid } : {}) }
  const claims = { iss: clientId, sub: clientId, aud: audience, iat: now, exp: now + 60, jti: randomBytes(16).toString('hex') }
  const input = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(claims))}`
  const sig = sign('sha256', Buffer.from(input), { key: createPrivateKey(privateKeyPem), dsaEncoding: 'ieee-p1363' })
  return `${input}.${b64url(sig)}`
}

/** The parsed event, or throws. Pass the RAW body (Buffer/string), not re-serialised JSON. */
export function verifyWebhook(payload, header, secret, toleranceSeconds = 300) {
  const body = Buffer.isBuffer(payload) ? payload : Buffer.from(payload)
  const parts = String(header ?? '').split(',').map(p => p.split('=')).filter(p => p.length === 2)
  const t = Number(parts.find(([k]) => k === 't')?.[1])
  if (!Number.isInteger(t)) throw new Error('Missing or malformed FOID-Signature header')
  if (Math.abs(Date.now() / 1000 - t) > toleranceSeconds) throw new Error('Webhook timestamp is outside the tolerance (possible replay)')
  const expected = createHmac('sha256', secret).update(`${t}.`).update(body).digest()
  const ok = parts.filter(([k]) => k === 'v1').some(([, v]) => {
    const got = Buffer.from(v, 'hex')
    return got.length === expected.length && timingSafeEqual(got, expected)
  })
  if (!ok) throw new Error("Webhook signature doesn't match")
  return JSON.parse(body.toString('utf8'))
}

export class Foid {
  /** clientId + clientSecret (or privateKeyPem): Continue with FOID.  apiKey: the Open API. */
  constructor({ apiKey, clientId, clientSecret, privateKeyPem, keyId, baseUrl = DEFAULT_BASE_URL, fetch: f } = {}) {
    Object.assign(this, { apiKey, clientId, clientSecret, privateKeyPem, keyId })
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this._fetch = f ?? globalThis.fetch
    this.oauth = { exchange: (code, codeVerifier, opts) => this.#exchange(code, codeVerifier, opts) }
    this.webhooks = { verify: verifyWebhook }
  }

  async #exchange(code, codeVerifier, { redirectUri } = {}) {
    if (!this.clientId) throw new Error('clientId is required')
    const url = `${this.baseUrl}/api/open/v1/oauth/token`
    const form = new URLSearchParams({ grant_type: 'authorization_code', code, code_verifier: codeVerifier })
    if (redirectUri) form.set('redirect_uri', redirectUri)
    const headers = { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'foid-node/0.1.0' }
    if (this.privateKeyPem) {
      form.set('client_id', this.clientId)
      form.set('client_assertion_type', ASSERTION_TYPE)
      form.set('client_assertion', clientAssertion(this.privateKeyPem, this.clientId, url, this.keyId))
    } else if (this.clientSecret) {
      headers.Authorization = 'Basic ' + Buffer.from(`${this.clientId}:${this.clientSecret}`).toString('base64')
    } else {
      throw new Error('Pass clientSecret, or privateKeyPem for a key-pair app')
    }
    const res = await this._fetch(url, { method: 'POST', headers, body: form })
    if (!res.ok) throw await toError(res)
    return res.json()
  }

  async request(method, path, { json, params, idempotencyKey } = {}) {
    if (!this.apiKey) throw new Error('apiKey is required for the Open API')
    const qs = params ? '?' + new URLSearchParams(params) : ''
    const res = await this._fetch(`${this.baseUrl}/api/open/v1${path}${qs}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`, 'User-Agent': 'foid-node/0.1.0',
        ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      },
      body: json !== undefined ? JSON.stringify(json) : undefined,
    })
    if (!res.ok) throw await toError(res)
    return res.status === 204 ? null : res.json()
  }

  getSubject(id) { return this.request('GET', `/subjects/${id}`) }
  createVerification({ idempotencyKey, ...body }) { return this.request('POST', '/verifications', { json: body, idempotencyKey }) }
  getVerification(id) { return this.request('GET', `/verifications/${id}`) }
  checkNin(body) { return this.request('POST', '/checks/nin', { json: body }) }
  checkBvn(body) { return this.request('POST', '/checks/bvn', { json: body }) }
}

export default Foid
