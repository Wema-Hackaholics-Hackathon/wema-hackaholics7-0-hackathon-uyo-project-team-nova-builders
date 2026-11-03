// Small shared pieces: JSON viewer, result box, field, pill.
import { useState } from 'react'

export function Json({ value }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function Pill({ tone = 'neutral', children }) {
  return <span className={`pill pill-${tone}`}>{children}</span>
}

// Runs an async action and shows its JSON result or error under the buttons.
export function useRunner() {
  const [state, setState] = useState({ busy: null, result: null, error: null, label: null })
  async function run(label, fn) {
    setState({ busy: label, result: null, error: null, label })
    try {
      const result = await fn()
      setState({ busy: null, result, error: null, label })
      return result
    } catch (e) {
      setState({ busy: null, result: null, error: e, label })
      return undefined
    }
  }
  return { ...state, run }
}

export function Output({ runner }) {
  if (runner.busy) return <p className="muted">Running {runner.busy}…</p>
  if (runner.error) {
    const e = runner.error
    return (
      <div className="out out-error">
        <div className="out-head"><b>{runner.label}</b><Pill tone="bad">{e.status ?? ''} {e.code || 'error'}</Pill></div>
        <p>{e.message}</p>
        {e.body && <Json value={e.body} />}
      </div>
    )
  }
  if (runner.result === null || runner.result === undefined) return null
  return (
    <div className="out">
      <div className="out-head"><b>{runner.label}</b><Pill tone="ok">ok</Pill></div>
      <Json value={runner.result} />
    </div>
  )
}

export function Card({ title, sub, right, children }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{title}</h2>
          {sub && <p className="sub">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}
