// Continue with FOID — every way @foid/react can start a sign-in, plus the two server-led flows.
// Whatever starts it, the browser only ever gets a one-time code; Harbor's backend exchanges it
// with the server SDK (client secret or key pair) and gets back who signed in.
import { useEffect, useState } from 'react'
import { ContinueWithFoid, FoidProvider, useFoidLogin } from '@foid/react'
import { createPkcePair, signInWithFoid } from '@foid/react/core'
import { api } from './api.js'
import { Card, Json, Pill } from './ui.jsx'

const SCOPES = [
  ['identity', 'NIN / BVN status, date of birth'],
  ['contact', 'email, masked phone'],
  ['liveness', 'liveness passed at'],
  ['financial', 'trust report access'],
]
export const SIGNIN_KEY = 'harbor_signin'   // our own note for redirect returns (method + nonce)
const newNonce = () => crypto.randomUUID().replaceAll('-', '')

export default function SignIn({ config, returned }) {
  const [method, setMethod] = useState(config.clientId ? 'secret' : 'keypair')
  const [scopes, setScopes] = useState(['identity'])
  const [nonce, setNonce] = useState(newNonce)
  const [outcome, setOutcome] = useState(returned)   // { data } | { error }
  const [busy, setBusy] = useState(false)
  const [pair, setPair] = useState(null)   // our own PKCE pair for the core-function demo

  // Made ahead of the click so window.open() still counts as user-initiated.
  useEffect(() => { createPkcePair().then(setPair) }, [nonce])

  useEffect(() => { if (returned) setOutcome(returned) }, [returned])

  const clientId = method === 'keypair' ? config.keypairClientId : config.clientId
  const scope = ['profile', ...scopes].join(' ')
  const redirectUri = `${window.location.origin}/callback`

  // Remember method + nonce in case the page leaves for a redirect (popup blocked / redirect mode).
  useEffect(() => {
    sessionStorage.setItem(SIGNIN_KEY, JSON.stringify({ method, nonce, redirect_uri: redirectUri }))
  }, [method, nonce, redirectUri])

  async function exchange(payload) {
    setBusy(true)
    try {
      const data = await api.exchange({ method, nonce, ...payload })
      setOutcome({ data })
    } catch (e) {
      setOutcome({ error: { code: e.code, message: e.message, body: e.body } })
    } finally {
      setBusy(false)
      setNonce(newNonce())
    }
  }

  // @foid/react made the PKCE pair → it hands back codeVerifier with the code.
  const onSuccess = ({ code, codeVerifier }) => exchange({ code, code_verifier: codeVerifier })
  const onError = (e) => setOutcome({ error: { code: e.code, message: e.message } })

  const options = { scope, nonce, onSuccess, onError }

  return (
    <FoidProvider clientId={clientId || ''} foidUrl={config.foidUrl}>
      <div className="grid-2">
        <Card title="Sign-in settings" sub="Applies to every button on this page.">
          <div className="seg">
            <button className={method === 'secret' ? 'on' : ''} onClick={() => setMethod('secret')}>
              Client secret
            </button>
            <button className={method === 'keypair' ? 'on' : ''} onClick={() => setMethod('keypair')}>
              Key pair (private_key_jwt)
            </button>
          </div>
          <p className="small muted">
            App: <code>{clientId || 'not set'}</code>
            {!clientId && <> — add {method === 'keypair' ? 'FOID_KEYPAIR_CLIENT_ID' : 'FOID_CLIENT_ID'} to <code>.env</code></>}
            {method === 'keypair' && !config.has.privateKey && <> · no key yet — make one in <b>Setup</b></>}
            {method === 'secret' && !config.has.clientSecret && <> · FOID_CLIENT_SECRET missing</>}
          </p>

          <div className="small strong">Scopes <span className="muted">(profile is always included)</span></div>
          <div className="checks">
            {SCOPES.map(([s, what]) => (
              <label key={s} title={what}>
                <input type="checkbox" checked={scopes.includes(s)}
                  onChange={() => setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))} />
                {s}
              </label>
            ))}
          </div>
          <p className="small muted">nonce for the next sign-in: <code>{nonce.slice(0, 12)}…</code> — checked against the result.</p>
        </Card>

        <Result outcome={outcome} busy={busy} onClear={() => setOutcome(null)} />
      </div>

      <div className="grid-2">
        <Card title="1 · <ContinueWithFoid />" sub="The drop-in button. Popup, PKCE made in the browser.">
          <div className="button-wall">
            <ContinueWithFoid {...options} />
            <ContinueWithFoid {...options} text="signin_with" theme="outline" />
            <ContinueWithFoid {...options} text="signup_with" size="medium" />
            <ContinueWithFoid {...options} text="verify_with" size="small" theme="outline" />
            <ContinueWithFoid {...options} width="100%" redirectUri={redirectUri} />
          </div>
          <p className="small muted">
            The last button also passes <code>redirectUri</code>: block popups for this site and it falls back to a
            full-page redirect, finished by <code>handleRedirectCallback()</code> on <code>/callback</code>.
          </p>
        </Card>

        <Card title="2 · useFoidLogin()" sub="Your own button, same flow.">
          <HookButton options={options} disabled={!clientId} />
          <p className="small muted">The hook exposes <code>pending</code> while the popup is open.</p>
        </Card>

        <Card title="3 · signInWithFoid() — no React" sub="From @foid/react/core, with our own PKCE pair.">
          <button className="btn" disabled={!clientId || !pair} onClick={async () => {
            // Pass only the challenge; the SDK returns codeVerifier: null because we kept it.
            try {
              const r = await signInWithFoid({ clientId, foidUrl: config.foidUrl, scope, nonce, codeChallenge: pair.codeChallenge })
              exchange({ code: r.code, code_verifier: pair.codeVerifier })
            } catch (e) { onError(e) }
          }}>Sign in with core function</button>
          <p className="small muted">Tests <code>createPkcePair()</code> + the <code>codeChallenge</code> option.</p>
        </Card>

        <Card title="4 · Server-led" sub="Harbor's backend runs create_pkce() and keeps the verifier + nonce.">
          <div className="row">
            <button className="btn" disabled={!clientId} onClick={() => serverLedPopup(method, scope, config.foidUrl, exchange, onError)}>
              Popup (web_message)
            </button>
            <button className="btn btn-ghost" disabled={!clientId} onClick={async () => {
              try {
                const { authorize_url } = await api.signinStart({ method, scope, redirect_uri: redirectUri })
                window.location.assign(authorize_url)
              } catch (e) { onError(e) }
            }}>
              Full-page redirect (query)
            </button>
          </div>
          <p className="small muted">The browser never sees the code verifier; the backend matches it by <code>state</code>.</p>
        </Card>
      </div>
    </FoidProvider>
  )
}

function HookButton({ options, disabled }) {
  const login = useFoidLogin(options)
  return (
    <button className="btn btn-dark" disabled={disabled || login.pending} onClick={login}>
      {login.pending ? 'Waiting for FOID…' : 'Log in to Harbor'}
    </button>
  )
}

// Popup opened from the click (so it isn't blocked), then pointed at the URL the backend built.
async function serverLedPopup(method, scope, foidUrl, exchange, onError) {
  const popup = window.open('', 'foid_sign_in', 'popup=yes,width=460,height=720')
  try {
    const { authorize_url, state } = await api.signinStart({ method, scope, origin: window.location.origin })
    if (!popup) throw Object.assign(new Error('Popup blocked — use the redirect button'), { code: 'popup_blocked' })
    popup.location.href = authorize_url
    const foidOrigin = new URL(foidUrl).origin
    const code = await new Promise((resolve, reject) => {
      const stop = () => { window.removeEventListener('message', onMsg); clearInterval(t) }
      function onMsg(e) {
        if (e.origin !== foidOrigin || e.source !== popup || e.data?.type !== 'foid:oauth') return
        stop()
        if (e.data.state !== state) reject(Object.assign(new Error('state mismatch'), { code: 'state_mismatch' }))
        else if (e.data.code) resolve(e.data.code)
        else reject(Object.assign(new Error('The person cancelled sign-in'), { code: e.data.error || 'access_denied' }))
      }
      window.addEventListener('message', onMsg)
      const t = setInterval(() => {
        if (popup.closed) { stop(); reject(Object.assign(new Error('The sign-in window was closed'), { code: 'popup_closed' })) }
      }, 500)
    })
    exchange({ code, state })
  } catch (e) {
    if (popup && !popup.closed) popup.close()
    onError(e)
  }
}

function Result({ outcome, busy, onClear }) {
  if (busy) return <Card title="Signing you in…" sub="Harbor's backend is exchanging the code with FOID." />
  if (!outcome) {
    return (
      <Card title="Not signed in" sub="Pick any button below. The result of the code exchange shows up here.">
        <ul className="small muted list">
          <li>Test apps: your real first and last name, everything else sandbox data.</li>
          <li>Codes live 60 seconds and work once — a replay revokes the grant.</li>
          <li>Errors to try: close the popup, press Cancel, or switch to an app with no key.</li>
        </ul>
      </Card>
    )
  }
  if (outcome.error) {
    return (
      <Card title="Sign-in didn't finish" right={<Pill tone="bad">{outcome.error.code || 'error'}</Pill>}>
        <p>{outcome.error.message}</p>
        {outcome.error.body && <Json value={outcome.error.body} />}
        <button className="btn btn-ghost btn-sm" onClick={onClear}>Clear</button>
      </Card>
    )
  }
  const { result, auth, server_led: serverLed, nonce_ok: nonceOk, backend } = outcome.data
  const s = result.subject || {}
  return (
    <Card title={`Welcome, ${[s.first_name, s.last_name].filter(Boolean).join(' ') || 'FOID user'}`}
      sub={`subject_id ${result.subject_id}`}
      right={<button className="btn btn-ghost btn-sm" onClick={onClear}>Sign out</button>}>
      <div className="pills">
        <Pill tone={result.sandbox ? 'warn' : 'ok'}>{result.sandbox ? 'sandbox data' : 'live data'}</Pill>
        <Pill>{auth}</Pill>
        <Pill>{serverLed ? 'server-led PKCE' : 'browser PKCE'}</Pill>
        <Pill>via {backend}</Pill>
        {nonceOk !== null && <Pill tone={nonceOk ? 'ok' : 'bad'}>{nonceOk ? 'nonce matches' : 'nonce mismatch'}</Pill>}
        <Pill tone={result.foid_account ? 'ok' : 'neutral'}>{result.foid_account ? 'has FOID account' : 'no FOID account'}</Pill>
        <Pill>scopes: {(result.scopes || []).join(', ')}</Pill>
      </div>
      <Json value={result} />
    </Card>
  )
}
