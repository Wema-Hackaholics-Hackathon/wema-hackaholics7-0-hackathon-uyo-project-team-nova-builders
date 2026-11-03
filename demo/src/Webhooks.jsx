// Events FOID sent to this backend's /webhooks/foid. The server SDK checks the FOID-Signature
// on the raw body before anything shows up here.
import { useEffect, useState } from 'react'
import { api } from './api.js'
import { Card, Json, Pill } from './ui.jsx'

export default function Webhooks({ config }) {
  const [log, setLog] = useState(null)
  const [err, setErr] = useState(null)
  const [live, setLive] = useState(true)
  const [open, setOpen] = useState(null)

  async function load() {
    try { setLog(await api.webhooks()); setErr(null) } catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!live) return undefined
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [live])

  // A delivery with a made-up signature: the SDK must reject it.
  async function forge() {
    const t = Math.floor(Date.now() / 1000)
    await fetch('/webhooks/foid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'FOID-Signature': `t=${t},v1=${'0'.repeat(64)}` },
      body: JSON.stringify({ id: 'evt_forged', type: 'verification.completed', data: {} }),
    })
    load()
  }

  const url = `${window.location.origin}/webhooks/foid`
  return (
    <Card title="Webhook deliveries" sub={<>FOID posts to <code>{url}</code> — register that URL in the console (test).</>}
      right={
        <div className="row">
          <label className="check-line small"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />live</label>
          <button className="btn btn-ghost btn-sm" onClick={forge}>Send a forged event</button>
          <button className="btn btn-ghost btn-sm" onClick={async () => { await api.clearWebhooks(); load() }}>Clear</button>
        </div>
      }>
      {!config.has.webhookSecret && (
        <p className="notice">No webhook secret for this backend yet — set FOID_WEBHOOK_SECRET_{config.backend.toUpperCase()} in <code>.env</code>.</p>
      )}
      <p className="small muted">
        Trigger events: console → Webhooks → <b>Send test event</b>, finish or cancel a verification, run a check,
        or revoke Harbor in the FOID app's Connected apps.
      </p>
      {err && <p className="notice bad">{err}</p>}
      {log && !log.events.length && <p className="muted">Waiting for the first delivery…</p>}
      <ul className="events">
        {log?.events.map((e, i) => (
          <li key={`${e.at}-${i}`} className={e.verified ? '' : 'rejected'}>
            <button className="event-row" onClick={() => setOpen(open === i ? null : i)}>
              <Pill tone={e.verified ? 'ok' : 'bad'}>{e.verified ? 'signature ok' : 'rejected'}</Pill>
              <b>{e.verified ? e.event.type : e.error}</b>
              <span className="muted small">{e.verified ? e.event.id : ''}</span>
              <span className="muted small push">{new Date(e.at * 1000).toLocaleTimeString()}</span>
            </button>
            {open === i && e.verified && <Json value={e.event} />}
          </li>
        ))}
      </ul>
    </Card>
  )
}
