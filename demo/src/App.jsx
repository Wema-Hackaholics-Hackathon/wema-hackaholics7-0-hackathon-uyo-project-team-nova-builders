// Harbor — a pretend digital bank that uses FOID. The page is served by either the Python or the
// Node backend; the accent colour tells you which (blue = Python, amber = Node).
import { useEffect, useState } from 'react'
import { handleRedirectCallback } from '@foid/react/core'
import { api } from './api.js'
import SignIn, { SIGNIN_KEY } from './SignIn.jsx'
import Verifications from './Verifications.jsx'
import Checks from './Checks.jsx'
import Subjects from './Subjects.jsx'
import Webhooks from './Webhooks.jsx'
import Setup from './Setup.jsx'

const TABS = [
  ['signin', 'Continue with FOID'],
  ['verifications', 'Verifications'],
  ['checks', 'NIN / BVN checks'],
  ['subjects', 'Subjects'],
  ['webhooks', 'Webhooks'],
  ['setup', 'Setup'],
]

// Back from a full-page redirect (/callback?code=&state=). Runs once, even under StrictMode.
let callbackOnce = null
function finishRedirect() {
  if (callbackOnce) return callbackOnce
  callbackOnce = (async () => {
    const q = new URLSearchParams(window.location.search)
    const note = JSON.parse(sessionStorage.getItem(SIGNIN_KEY) || '{}')
    window.history.replaceState({}, '', '/?tab=signin')
    try {
      // 1. Started by @foid/react (popup was blocked): the SDK kept state + verifier in sessionStorage.
      const r = handleRedirectCallback(`?${q}`)
      const payload = r
        ? { code: r.code, code_verifier: r.codeVerifier, method: note.method, nonce: note.nonce, redirect_uri: note.redirect_uri }
        // 2. Started by our backend (server-led redirect): it matches the verifier by state.
        : q.get('code') ? { code: q.get('code'), state: q.get('state') } : null
      if (!payload) return { error: { code: q.get('error') || 'access_denied', message: 'Sign-in was cancelled' } }
      return { data: await api.exchange(payload) }
    } catch (e) {
      return { error: { code: e.code, message: e.message, body: e.body } }
    }
  })()
  return callbackOnce
}

export default function App() {
  const [config, setConfig] = useState(null)
  const [down, setDown] = useState(null)
  const [tab, setTab] = useState(() => new URLSearchParams(window.location.search).get('tab') || 'signin')
  const [returned, setReturned] = useState(null)

  const load = () => api.config().then((c) => { setConfig(c); setDown(null) }).catch((e) => setDown(e.message))
  useEffect(() => { load() }, [])

  useEffect(() => {
    if (window.location.pathname === '/callback') finishRedirect().then(setReturned)
  }, [])

  useEffect(() => {
    if (config) document.documentElement.dataset.backend = config.backend
  }, [config])

  const pick = (t) => {
    setTab(t)
    window.history.replaceState({}, '', `/?tab=${t}`)
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="logo">H</span>
          <div>
            <div className="brand-name">Harbor</div>
            <div className="brand-tag">FOID SDK demo</div>
          </div>
        </div>
        {config && (
          <div className="backend-badge">
            <span className="dot" />
            {config.backend === 'python' ? 'Python backend' : 'Node backend'}
            <span className="muted">{config.sdk.package} {config.sdk.version}</span>
          </div>
        )}
      </header>

      <nav className="tabs">
        {TABS.map(([k, label]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => pick(k)}>{label}</button>
        ))}
      </nav>

      <main className="content">
        {down && <p className="notice bad">Can't reach Harbor's backend: {down}</p>}
        {!config && !down && <p className="muted">Loading…</p>}
        {config && (
          <>
            {tab === 'signin' && <SignIn config={config} returned={returned} />}
            {tab === 'verifications' && <Verifications config={config} />}
            {tab === 'checks' && <Checks />}
            {tab === 'subjects' && <Subjects />}
            {tab === 'webhooks' && <Webhooks config={config} />}
            {tab === 'setup' && <Setup config={config} reload={load} />}
          </>
        )}
      </main>

      <footer className="foot">
        The browser only gets public client IDs. API key, client secret and private key stay on Harbor's backend.
      </footer>
    </div>
  )
}
