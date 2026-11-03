// Server-to-server checks: Harbor attests it already has the person's consent (check_nin / check_bvn).
import { useState } from 'react'
import { api } from './api.js'
import { Card, Field, Output, useRunner } from './ui.jsx'

export default function Checks() {
  const [kind, setKind] = useState('nin')
  const [f, setF] = useState({
    number: '', first_name: 'Ada', last_name: 'Obi', date_of_birth: '1994-03-12',
    customer_ref: 'cust_1001', purpose: 'Open a Harbor savings account', consent_obtained: true,
  })
  const r = useRunner()
  const set = (k) => (e) => setF({ ...f, [k]: k === 'number' ? e.target.value.replace(/\D/g, '').slice(0, 11) : e.target.value })

  return (
    <div className="grid-2">
      <Card title="NIN / BVN check" sub="Test mode always passes with sandbox data.">
        <div className="seg">
          <button className={kind === 'nin' ? 'on' : ''} onClick={() => setKind('nin')}>check_nin</button>
          <button className={kind === 'bvn' ? 'on' : ''} onClick={() => setKind('bvn')}>check_bvn</button>
        </div>
        <Field label={`${kind.toUpperCase()} (11 digits)`}><input inputMode="numeric" value={f.number} onChange={set('number')} placeholder="12345678901" /></Field>
        <div className="grid-2 tight">
          <Field label="First name"><input value={f.first_name} onChange={set('first_name')} /></Field>
          <Field label="Last name"><input value={f.last_name} onChange={set('last_name')} /></Field>
          <Field label="Date of birth"><input type="date" value={f.date_of_birth} onChange={set('date_of_birth')} /></Field>
          <Field label="Customer ref"><input value={f.customer_ref} onChange={set('customer_ref')} /></Field>
        </div>
        <Field label="Consent purpose"><input value={f.purpose} onChange={set('purpose')} /></Field>
        <label className="check-line">
          <input type="checkbox" checked={f.consent_obtained} onChange={(e) => setF({ ...f, consent_obtained: e.target.checked })} />
          The customer agreed to this check (untick to see the API refuse it)
        </label>
        <button className="btn" onClick={() => r.run(`check_${kind}`, () => api.check(kind, f))}>Run check</button>
      </Card>
      <Card title="Response" sub="The subject_id here works on the Subjects tab.">
        <Output runner={r} />
        {!r.result && !r.error && !r.busy && <p className="muted small">Nothing yet.</p>}
      </Card>
    </div>
  )
}
