// The people Harbor has verified. Every read goes through FOID's consent checks.
import { useState } from 'react'
import { api } from './api.js'
import { Card, Field, Output, useRunner } from './ui.jsx'

export default function Subjects() {
  const [id, setId] = useState('')
  const [ref, setRef] = useState('')
  const list = useRunner()
  const r = useRunner()
  const go = (label, fn) => r.run(label, fn)

  return (
    <div className="grid-2">
      <Card title="Subjects" sub="GET /subjects" right={
        <div className="row">
          <input placeholder="customer_ref filter" value={ref} onChange={(e) => setRef(e.target.value)} />
          <button className="btn btn-sm" onClick={() => list.run('list subjects', () => api.listSubjects({ customer_ref: ref }))}>Load</button>
        </div>
      }>
        {list.result?.data ? (
          <table className="table">
            <thead><tr><th>subject</th><th>name</th><th>ref</th><th /></tr></thead>
            <tbody>
              {list.result.data.map((s) => (
                <tr key={s.id}>
                  <td><code>{s.id}</code></td>
                  <td>{[s.first_name, s.last_name].filter(Boolean).join(' ') || '—'}</td>
                  <td>{s.customer_ref || '—'}</td>
                  <td><button className="btn btn-ghost btn-sm" onClick={() => setId(s.id)}>Use</button></td>
                </tr>
              ))}
              {!list.result.data.length && <tr><td colSpan={4} className="muted">None yet — run a check or verification.</td></tr>}
            </tbody>
          </table>
        ) : <Output runner={list} />}
      </Card>

      <Card title="One subject" sub="Revoked consent → 403 consent_revoked.">
        <Field label="subject_id"><input value={id} onChange={(e) => setId(e.target.value.trim())} placeholder="sub_…" /></Field>
        <div className="row wrap">
          <button className="btn" disabled={!id} onClick={() => go('get_subject', () => api.getSubject(id))}>get_subject</button>
          <button className="btn btn-ghost" disabled={!id} onClick={() => go('subject checks', () => api.subjectChecks(id))}>Checks</button>
          <button className="btn btn-ghost" disabled={!id} onClick={() => go('trust report', () => api.trustReport(id))}>Trust report</button>
          <button className="btn btn-danger" disabled={!id} onClick={() => {
            if (confirm(`Erase ${id} and everything FOID holds about them for Harbor?`)) go('delete subject', () => api.deleteSubject(id))
          }}>Delete</button>
        </div>
        <p className="small muted">Trust report needs the <code>financial</code> scope and a FOID account holder (sign in with that scope first).</p>
        <Output runner={r} />
      </Card>
    </div>
  )
}
