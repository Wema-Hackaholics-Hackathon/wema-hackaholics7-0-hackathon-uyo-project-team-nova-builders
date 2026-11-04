// Continue with FOID — framework-free browser core (used by the React bindings; usable on its own).
// The popup returns a one-time `code`; send { code, codeVerifier } to YOUR server, which exchanges it with
// @foid/node or the foid Python SDK. Never exchange in the browser — that needs your client secret.

export const DEFAULT_FOID_URL = 'https://usefoid.pages.dev'

export class FoidSignInError extends Error {
  constructor(code, message) { super(message || code); this.code = code }
}

const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const random = (n) => b64url(crypto.getRandomValues(new Uint8Array(n)))

/** PKCE S256 pair made in the browser. */
export async function createPkcePair() {
  const codeVerifier = random(48)
  const codeChallenge = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(codeVerifier)))
  return { codeVerifier, codeChallenge }
}

function authorizeUrl(foidUrl, p) {
  const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v != null && v !== ''))
  return `${foidUrl.replace(/\/$/, '')}/oauth/authorize?${q}`
}

const STORE = 'foid_oauth_pending'

/**
 * Open the FOID sign-in popup. Call it straight from a click handler (popup blockers).
 * Resolves { code, state, codeVerifier } — codeVerifier is null if you passed your own codeChallenge.
 * Popup blocked + redirectUri given → falls back to a full-page redirect (see handleRedirectCallback).
 */
export function signInWithFoid({
  clientId, foidUrl = DEFAULT_FOID_URL, scope = 'profile', nonce, state, codeChallenge,
  redirectUri, width = 460, height = 720,
}) {
  if (!clientId) return Promise.reject(new FoidSignInError('missing_client_id', 'clientId is required'))
  const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2)
  const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2)
  const popup = window.open('', 'foid_sign_in', `popup=yes,width=${width},height=${height},left=${left},top=${top}`)
  const st = state || random(16)
  const foidOrigin = new URL(foidUrl).origin

  return (async () => {
    let verifier = null
    let challenge = codeChallenge
    if (!challenge) ({ codeVerifier: verifier, codeChallenge: challenge } = await createPkcePair())
    const common = { client_id: clientId, scope, state: st, nonce, code_challenge: challenge, code_challenge_method: 'S256' }

    if (!popup) {
      if (!redirectUri) throw new FoidSignInError('popup_blocked', 'The sign-in popup was blocked — allow popups for this site')
      sessionStorage.setItem(STORE, JSON.stringify({ state: st, codeVerifier: verifier }))
      window.location.assign(authorizeUrl(foidUrl, { ...common, response_mode: 'query', redirect_uri: redirectUri }))
      return new Promise(() => {})   // the page is navigating away
    }
    popup.location.href = authorizeUrl(foidUrl, { ...common, response_mode: 'web_message', origin: window.location.origin })

    return await new Promise((resolve, reject) => {
      const done = (fn) => { window.removeEventListener('message', onMessage); clearInterval(timer); fn() }
      function onMessage(e) {
        if (e.origin !== foidOrigin || e.source !== popup || e.data?.type !== 'foid:oauth') return
        if (e.data.state !== st) return done(() => reject(new FoidSignInError('state_mismatch', 'Sign-in response did not match this request')))
        if (e.data.code) done(() => resolve({ code: e.data.code, state: st, codeVerifier: verifier }))
        else done(() => reject(new FoidSignInError(e.data.error || 'access_denied', 'The person cancelled sign-in')))
      }
      window.addEventListener('message', onMessage)
      const timer = setInterval(() => {
        if (popup.closed) done(() => reject(new FoidSignInError('popup_closed', 'The sign-in window was closed')))
      }, 500)
    })
  })().catch((err) => { if (popup && !popup.closed) popup.close(); throw err })
}

/** On your redirectUri page (redirect fallback): { code, state, codeVerifier } or null if this isn't a FOID return. */
export function handleRedirectCallback(search = window.location.search) {
  const q = new URLSearchParams(search)
  const pending = JSON.parse(sessionStorage.getItem(STORE) || 'null')
  if (!pending || !q.get('state')) return null
  sessionStorage.removeItem(STORE)
  if (q.get('state') !== pending.state) throw new FoidSignInError('state_mismatch', 'Sign-in response did not match this request')
  if (!q.get('code')) throw new FoidSignInError(q.get('error') || 'access_denied', 'The person cancelled sign-in')
  return { code: q.get('code'), state: pending.state, codeVerifier: pending.codeVerifier }
}
