// What Harbor's backend has configured, and the values to paste into the FOID console.
import { useEffect, useState } from 'react'
import { api } from './api.js'
import { Card, Json, Output, Pill, useRunner } from './ui.jsx'

function Copy({ text }) {
  const [done, setDone] = useState(false)
  return (
    <button className="btn btn-ghost btn-sm" onClick={async () => {
      await navigator.clipboard.writeText(text)
      setDone(true)
      setTimeout(() => setDone(false), 1500)
    }}>{done ? 'Copied' : 'Copy'}</button>
  )
}

export default function Setup({ config, reload }) {
  const ping = useRunner()
  const [kp, setKp] = useState(null)
  const [kpErr, setKpErr] = useState(null)
  useEffect(() => { api.keypair().then(setKp).catch(() => {}) }, [])

  const origin = window.location.origin
  const rows = [
    ['FOID_API_KEY', config.has.apiKey, 'Console → API keys → Create (test)'],
    ['FOID_CLIENT_ID + FOID_CLIENT_SECRET', !!config.clientId && config.has.clientSecret, 'Console → Sign-in apps → Create app (test)'],
    ['FOID_KEYPAIR_CLIENT_ID', !!config.keypairClientId, 'A second sign-in app, switched to Key pair'],
    ['keys/private_key.pem', config.has.privateKey, 'Generate below'],
    [`FOID_WEBHOOK_SECRET_${config.backend.toUpperCase()}`, config.has.webhookSecret, 'Console → Webhooks → Add endpoint (test)'],
  ]
  const jwk = kp?.public_jwk ? JSON.stringify(kp.public_jwk, null, 2) : null

  return (
    <div className="grid-2">
      <Card title="Configuration" sub={`${config.sdk.package} ${config.sdk.version} · FOID API ${config.apiUrl} · popup ${config.foidUrl}`}
        right={<button className="btn btn-ghost btn-sm" onClick={reload}>Reload</button>}>
        <table className="table">
          <tbody>
            {rows.map(([k, ok, how]) => (
              <tr key={k}>
                <td><code>{k}</code></td>
                <td><Pill tone={ok ? 'ok' : 'warn'}>{ok ? 'set' : 'missing'}</Pill></td>
                <td className="small muted">{how}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">Edit <code>demo/.env</code>, then restart this backend (<code>docker compose up {config.backend}</code>).</p>
        <button className="btn" onClick={() => ping.run('GET /ping (API key)', api.ping)}>Test API key</button>
        <Output runner={ping} />
      </Card>

      <div className="stack">
        <Card title="Paste into the console" sub="Test apps already accept any localhost origin; registering is still tidy.">
          <table className="table">
            <tbody>
              <tr><td>Allowed origin</td><td><code>{origin}</code></td><td><Copy text={origin} /></td></tr>
              <tr><td>Redirect URI</td><td><code>{origin}/callback</code></td><td><Copy text={`${origin}/callback`} /></td></tr>
              <tr><td>Webhook URL</td><td><code>{origin}/webhooks/foid</code></td><td><Copy text={`${origin}/webhooks/foid`} /></td></tr>
            </tbody>
          </table>
        </Card>

        <Card title="Key pair (private_key_jwt)" sub="generate_keypair() / generateKeyPair() from the SDK. The private key never leaves keys/.">
          {jwk ? (
            <>
              <div className="row"><span className="small">Public JWK — paste in Sign-in apps → Edit → Key pair</span><Copy text={jwk} /></div>
              <Json value={kp.public_jwk} />
            </>
          ) : (
            <button className="btn" onClick={async () => {
              try { setKp(await api.makeKeypair()); setKpErr(null); reload() } catch (e) { setKpErr(e.message) }
            }}>Generate key pair</button>
          )}
          {kp?.exists && !jwk && <p className="small muted">A private key exists but its public JWK file is missing.</p>}
          {kpErr && <p className="notice bad">{kpErr}</p>}
          <p className="small muted">Both backends share <code>demo/keys/</code>, so one key pair app works with Python and Node.</p>
        </Card>
      </div>
    </div>
  )
}
