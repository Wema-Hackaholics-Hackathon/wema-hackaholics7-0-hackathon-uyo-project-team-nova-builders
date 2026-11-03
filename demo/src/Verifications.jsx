// Hosted verification: Harbor's backend creates it (create_verification), the person finishes it on
// FOID's page — in a new tab or embedded with foid-verify.js — and Harbor reads the result back.
import { useState } from 'react'
import { api } from './api.js'
import { Card, Field, Output, Pill, useRunner } from './ui.jsx'

const CHECKS = ['nin', 'bvn', 'liveness', 'reverify']
const EXTRA_SCOPES = ['contact', 'financial']
const STATUSES = ['', 'pending', 'in_progress', 'completed', 'cancelled', 'expired']
const newKey = () => `harbor-${crypto.randomUUID().slice(0, 8)}`

function loadEmbed(foidUrl) {
  if (window.FoidVerify) return Promise.resolve(window.FoidVerify)
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = `${foidUrl.replace(/\/$/, '')}/foid-verify.js`
    s.onload = () => resolve(window.FoidVerify)
    s.onerror = () => reject(new Error(`Couldn't load ${s.src} — is the FOID app running?`))
    document.head.appendChild(s)
  })
}

export default function Verifications({ config }) {
  const [form, setForm] = useState({
    checks: ['nin', 'liveness'], scopes: [], purpose: 'Open a Harbor savings account',
    customer_ref: 'cust_1001', first_name: 'Ada', last_name: 'Obi', email: '', subject_id: '',
    idempotency_key: newKey(),
  })
  const [current, setCurrent] = useState(null)
  const [filter, setFilter] = useState('')
  const [embedNote, setEmbedNote] = useState(null)
  const create = useRunner()
  const act = useRunner()
  const list = useRunner()

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const toggle = (k, v) => setForm({ ...form, [k]: form[k].includes(v) ? form[k].filter((x) => x !== v) : [...form[k], v] })
  const payload = () => ({ ...form, return_url: `${window.location.origin}/?tab=verifications` })

  async function submit(twice) {
    const r = await create.run(twice ? 'create_verification ×2 (same Idempotency-Key)' : 'create_verification', async () => {
      const first = await api.createVerification(payload())
      if (!twice) return first
      const second = await api.createVerification(payload())
      return { same_verification: first.id === second.id, first, second }
    })
    const v = r && (r.first || r)
    if (v?.id) setCurrent(v)
  }

  async function embed() {
    setEmbedNote(null)
    try {
      const FoidVerify = await loadEmbed(config.foidUrl)
      FoidVerify.open({
        clientToken: current.client_token,
        origin: config.foidUrl,
        onComplete: (r) => { setEmbedNote(`onComplete: ${r.outcome || r.status} — confirming on the server…`); refresh() },
        onCancel: () => setEmbedNote('onCancel: the person left the flow'),
      })
    } catch (e) { setEmbedNote(e.message) }
  }

  const refresh = () => act.run('get_verification', async () => {
    const v = await api.getVerification(current.id)
    setCurrent(v)
    return v
  })

  return (
    <div className="grid-2">
      <Card title="Start a verification" sub="POST /verifications through the server SDK.">
        <div className="small strong">Checks</div>
        <div className="checks">
          {CHECKS.map((c) => (
            <label key={c}><input type="checkbox" checked={form.checks.includes(c)} onChange={() => toggle('checks', c)} />{c}</label>
          ))}
        </div>
        <div className="small strong">Extra scopes</div>
        <div className="checks">
          {EXTRA_SCOPES.map((c) => (
            <label key={c}><input type="checkbox" checked={form.scopes.includes(c)} onChange={() => toggle('scopes', c)} />{c}</label>
          ))}
        </div>
        <Field label="Purpose (shown to the person)"><input value={form.purpose} onChange={set('purpose')} /></Field>
        <div className="grid-2 tight">
          <Field label="Your customer ref"><input value={form.customer_ref} onChange={set('customer_ref')} /></Field>
          <Field label="Existing subject_id" hint="needed for reverify"><input value={form.subject_id} onChange={set('subject_id')} /></Field>
          <Field label="First name"><input value={form.first_name} onChange={set('first_name')} /></Field>
          <Field label="Last name"><input value={form.last_name} onChange={set('last_name')} /></Field>
        </div>
        <Field label="Idempotency-Key" hint="same key + same body = the same verification back">
          <div className="row">
            <input value={form.idempotency_key} onChange={set('idempotency_key')} />
            <button className="btn btn-ghost btn-sm" onClick={() => setForm({ ...form, idempotency_key: newKey() })}>New</button>
          </div>
        </Field>
        <div className="row">
          <button className="btn" onClick={() => submit(false)}>Create verification</button>
          <button className="btn btn-ghost" onClick={() => submit(true)}>Send twice</button>
        </div>
        <Output runner={create} />
      </Card>

      <div className="stack">
        <Card title="Current verification" sub={current ? current.id : 'Create one to continue.'}
          right={current && <Pill tone={current.status === 'completed' ? 'ok' : 'neutral'}>{current.status}</Pill>}>
          {current && (
            <>
              <div className="row wrap">
                <a className={`btn ${current.hosted_url ? '' : 'disabled'}`} href={current.hosted_url || undefined} target="_blank" rel="noreferrer">
                  Open hosted page
                </a>
                <button className="btn btn-ghost" disabled={!current.client_token} onClick={embed}>Embed (foid-verify.js)</button>
                <button className="btn btn-ghost" onClick={refresh}>Refresh</button>
                <button className="btn btn-danger" onClick={() => act.run('cancel', async () => {
                  const v = await api.cancelVerification(current.id)
                  setCurrent({ ...current, ...v })
                  return v
                })}>Cancel</button>
              </div>
              {!current.hosted_url && <p className="small muted">No link: the verification is closed.</p>}
              {embedNote && <p className="small">{embedNote}</p>}
              <Output runner={act} />
            </>
          )}
        </Card>

        <Card title="All verifications" sub="GET /verifications (request() helper)." right={
          <div className="row">
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || 'any status'}</option>)}
            </select>
            <button className="btn btn-sm" onClick={() => list.run('list verifications', () => api.listVerifications({ status: filter }))}>Load</button>
          </div>
        }>
          {list.result?.data ? (
            <table className="table">
              <thead><tr><th>id</th><th>status</th><th>checks</th><th /></tr></thead>
              <tbody>
                {list.result.data.map((v) => (
                  <tr key={v.id}>
                    <td><code>{v.id}</code></td>
                    <td>{v.status}</td>
                    <td>{(v.checks || []).join(', ')}</td>
                    <td><button className="btn btn-ghost btn-sm" onClick={() => setCurrent(v)}>Use</button></td>
                  </tr>
                ))}
                {!list.result.data.length && <tr><td colSpan={4} className="muted">None yet.</td></tr>}
              </tbody>
            </table>
          ) : <Output runner={list} />}
        </Card>
      </div>
    </div>
  )
}
