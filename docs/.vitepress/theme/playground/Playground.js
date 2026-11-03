// The live "Continue with FOID" playground. Real @foid/react button, real FOID popup, and the real
// exchange result, using FOID's built-in docs test app (real name, sandbox data for everything else).
// Written with createElement (no JSX) so it needs no extra build setup inside VitePress.
import { createElement as h, useEffect, useMemo, useState } from 'react'
import { ContinueWithFoid, FoidProvider, useFoidLogin } from '@foid/react'

const API = (import.meta.env.VITE_FOID_API_URL || '').replace(/\/$/, '')
const EXTRA_SCOPES = ['identity', 'contact', 'liveness', 'financial']
const TEXTS = { continue_with: 'Continue with FOID', signin_with: 'Sign in with FOID', signup_with: 'Sign up with FOID', verify_with: 'Verify with FOID' }
const ERRORS = {
  popup_closed: 'The person closed the FOID window before finishing.',
  access_denied: 'The person pressed Cancel on the consent screen.',
  popup_blocked: 'The browser blocked the popup. Pass redirectUri to fall back to a full-page redirect.',
  state_mismatch: 'The response did not match this sign-in (possible CSRF) — it was ignored.',
  missing_client_id: 'No clientId was passed to <FoidProvider>.',
}

function reactSnippet(o) {
  const props = [
    o.text !== 'continue_with' && `text="${o.text}"`,
    o.theme !== 'filled' && `theme="${o.theme}"`,
    o.size !== 'large' && `size="${o.size}"`,
    o.width && `width="${o.width}"`,
    `scope="${o.scope}"`,
  ].filter(Boolean)
  const btn = o.custom
    ? `function LoginButton() {
  const login = useFoidLogin({
    scope: '${o.scope}',
    onSuccess: ({ code, codeVerifier }) =>
      fetch('/auth/foid', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, codeVerifier }) }),
    onError: (e) => console.log(e.code),
  })
  return <button onClick={login} disabled={login.pending}>Log in with FOID</button>
}`
    : `<ContinueWithFoid
  ${props.join('\n  ')}
  onSuccess={({ code, codeVerifier }) =>
    fetch('/auth/foid', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, codeVerifier }) })}
  onError={(e) => console.log(e.code)}   // popup_closed | access_denied | …
/>`
  return `import { FoidProvider, ${o.custom ? 'useFoidLogin' : 'ContinueWithFoid'} } from '@foid/react'

// <FoidProvider> once, near the root of your app. Only the PUBLIC client ID goes in the browser.
<FoidProvider clientId="foid_app_test_…" foidUrl="https://app.foid.ng">
  …
</FoidProvider>

${btn}`
}

const NODE = `// POST /auth/foid on YOUR server — the client secret never reaches the browser
import { Foid } from '@foid/node'

const foid = new Foid({
  clientId: process.env.FOID_CLIENT_ID,
  clientSecret: process.env.FOID_CLIENT_SECRET,
  baseUrl: 'https://api.foid.ng',
})

app.post('/auth/foid', async (req, res) => {
  const { code, codeVerifier } = req.body
  const person = await foid.oauth.exchange(code, codeVerifier)   // once, within 60 s
  // person.subject_id is stable for your business — use it as the FOID link on your user
  res.json({ name: \`\${person.subject.first_name} \${person.subject.last_name}\` })
})`

const PYTHON = `# POST /auth/foid on YOUR server — the client secret never reaches the browser
import os
from fastapi import FastAPI
from foid import Foid

foid = Foid(client_id=os.environ["FOID_CLIENT_ID"],
            client_secret=os.environ["FOID_CLIENT_SECRET"],
            base_url="https://api.foid.ng")
app = FastAPI()

@app.post("/auth/foid")
def sign_in(body: dict):
    person = foid.oauth.exchange(body["code"], body["codeVerifier"])   # once, within 60 s
    # person["subject_id"] is stable for your business — store it on your user
    return {"name": f'{person["subject"]["first_name"]} {person["subject"]["last_name"]}'}`

function Code({ text }) {
  const [copied, setCopied] = useState(false)
  return h('div', { style: { position: 'relative' } },
    h('button', {
      onClick: () => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400) }),
      style: { position: 'absolute', top: 8, right: 10, fontSize: 12, color: '#d9c6e6' },
    }, copied ? 'Copied' : 'Copy'),
    h('pre', { className: 'foid-pg-code' }, text))
}

function HookButton({ options }) {
  const login = useFoidLogin(options)
  return h('button', {
    onClick: login, disabled: login.pending,
    style: { padding: '10px 18px', borderRadius: 10, background: '#16101c', color: '#fff', fontWeight: 600 },
  }, login.pending ? 'Waiting for FOID…' : 'Log in with FOID (your own button)')
}

export default function Playground({ compact = false }) {
  const [cfg, setCfg] = useState(null)
  const [down, setDown] = useState(null)
  const [o, setO] = useState({ text: 'continue_with', theme: 'filled', size: 'large', width: '', custom: false })
  const [scopes, setScopes] = useState(['identity'])
  const [tab, setTab] = useState('react')
  const [out, setOut] = useState(null)   // { result } | { error, message }
  const [busy, setBusy] = useState(false)
  const [nonce, setNonce] = useState(() => crypto.randomUUID())   // checked against result.nonce

  useEffect(() => {
    fetch(`${API}/api/v1/docs-playground/config`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setCfg)
      .catch((e) => setDown(String(e.message || e)))
  }, [])

  const scope = ['profile', ...scopes].join(' ')
  const snippet = useMemo(() => reactSnippet({ ...o, scope }), [o, scope])

  async function onSuccess({ code, codeVerifier }) {
    setBusy(true)
    setOut(null)
    try {
      const r = await fetch(`${API}/api/v1/docs-playground/exchange`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, code_verifier: codeVerifier }),
      })
      const data = await r.json()
      setOut(r.ok ? { result: data, nonceOk: data.nonce === nonce } : { error: data.error, message: data.error_description })
    } catch (e) {
      setOut({ error: 'network_error', message: String(e.message || e) })
    } finally {
      setBusy(false)
      setNonce(crypto.randomUUID())
    }
  }
  const onError = (e) => setOut({ error: e.code, message: ERRORS[e.code] || e.message })
  const options = { scope, nonce, onSuccess, onError }

  if (down) {
    return h('div', { className: 'foid-pg foid-pg-offline' },
      h('b', null, 'The playground needs a FOID backend. '),
      `Couldn't reach ${API || ''}/api/v1/docs-playground/config (${down}). Locally: run the backend (port 8000) and the FOID user app (port 5173), then reload.`)
  }
  if (!cfg) return h('div', { className: 'foid-pg foid-pg-offline' }, 'Connecting to FOID…')

  const set = (k) => (e) => setO({ ...o, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const select = (k, values) => h('select', { value: o[k], onChange: set(k) },
    Object.entries(values).map(([v, label]) => h('option', { key: v, value: v }, label)))

  const controls = h('div', { className: 'foid-pg-controls' },
    h('h4', null, 'Button'),
    h('label', null, h('input', { type: 'checkbox', checked: o.custom, onChange: set('custom') }), 'Use my own button (useFoidLogin)'),
    !o.custom && h('div', null,
      h('h4', null, 'text'), select('text', TEXTS),
      h('h4', null, 'theme'), select('theme', { filled: 'filled', outline: 'outline' }),
      h('h4', null, 'size'), select('size', { large: 'large', medium: 'medium', small: 'small' }),
      h('h4', null, 'width'), select('width', { '': 'auto', '260': '260', '100%': '100%' })),
    h('h4', null, 'scope'),
    h('label', { title: 'Always included' }, h('input', { type: 'checkbox', checked: true, disabled: true }), 'profile — name'),
    EXTRA_SCOPES.map((s) => h('label', { key: s, title: cfg.scopes?.[s] },
      h('input', { type: 'checkbox', checked: scopes.includes(s), onChange: () => setScopes((c) => (c.includes(s) ? c.filter((x) => x !== s) : [...c, s])) }),
      s)))

  const preview = h('div', { className: 'foid-pg-preview' },
    h(FoidProvider, { clientId: cfg.client_id, foidUrl: cfg.foid_url },
      o.custom
        ? h(HookButton, { options })
        : h(ContinueWithFoid, { ...options, text: o.text, theme: o.theme, size: o.size, width: o.width || undefined })))

  const result = busy
    ? h('div', { className: 'foid-pg-result' }, 'Exchanging the code…')
    : out?.result
      ? h('div', { className: 'foid-pg-result ok' },
          h('h5', null, h('span', { className: 'foid-pg-pill ok' }, '200'),
            h('span', { className: `foid-pg-pill ${out.nonceOk ? 'ok' : 'err'}` }, out.nonceOk ? 'nonce matches' : 'nonce mismatch'),
            `Signed in as ${out.result.subject?.first_name ?? ''} ${out.result.subject?.last_name ?? ''}`),
          h('p', { className: 'foid-pg-note' }, 'This is exactly what your server gets back from foid.oauth.exchange(). Test mode: only the name is real.'),
          h(Code, { text: JSON.stringify(out.result, null, 2) }))
      : out
        ? h('div', { className: 'foid-pg-result err' },
            h('h5', null, h('span', { className: 'foid-pg-pill err' }, out.error), 'Sign-in did not finish'),
            h('p', { className: 'foid-pg-note' }, out.message))
        : h('p', { className: 'foid-pg-note' },
            'Click the button: the real FOID window opens. Sign in with your FOID email, approve, and the result appears here. Try Cancel or closing the window to see the errors.')

  const code = h('div', null,
    h('div', { className: 'foid-pg-tabs' },
      [['react', 'React'], ['node', 'Server · Node'], ['python', 'Server · Python']].map(([k, label]) =>
        h('button', { key: k, className: tab === k ? 'on' : '', onClick: () => setTab(k) }, label))),
    h('div', { style: { marginTop: 10 } }, h(Code, { text: tab === 'react' ? snippet : tab === 'node' ? NODE : PYTHON })))

  return h('div', { className: 'foid-pg' },
    h('div', { className: compact ? '' : 'foid-pg-grid' },
      !compact && controls,
      h('div', { className: 'foid-pg-stage' }, preview, result, !compact && code)))
}
