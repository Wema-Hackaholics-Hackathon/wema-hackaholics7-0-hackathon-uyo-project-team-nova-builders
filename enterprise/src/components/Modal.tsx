/** Centered dialog (bottom sheet on phones) + the pieces the console's dialogs share. */
import { useEffect, useState, type ReactNode } from 'react'
import RemixIcon from './RemixIcon'
import { Button } from './ui'

export default function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/45 sm:p-4" role="dialog" aria-modal="true"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full sm:max-w-[480px] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100">
          <h2 className="text-[17px] font-bold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-neutral-100">
            <RemixIcon name="ri-close-line" size={20} color="#71717a" />
          </button>
        </div>
        <div className="p-6 flex flex-col gap-4">{children}</div>
      </div>
    </div>
  )
}

/** A secret that is shown exactly once (API key, webhook signing secret). */
export function SecretOnce({ secret, what, onDone }: { secret: string; what: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)
  return (
    <>
      <p className="flex gap-2 rounded-xl bg-orange-50 border border-orange-200 p-3 text-[12.5px] text-orange-700">
        <RemixIcon name="ri-error-warning-line" size={17} />
        Copy this {what} now. FOID doesn’t keep it, so it can’t be shown again — if you lose it, create a new one.
      </p>
      <div className="flex items-center gap-2 rounded-xl bg-neutral-50 border border-neutral-200 p-2">
        <code className="flex-1 break-all text-[12.5px] font-mono px-1">{secret}</code>
        <button onClick={() => { void navigator.clipboard.writeText(secret); setCopied(true) }}
          className="shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white bg-[#C800DE]">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} className="accent-[#C800DE]" />
        I’ve stored it somewhere safe
      </label>
      <span className={saved ? '' : 'opacity-50 pointer-events-none'}><Button onClick={onDone}>Done</Button></span>
    </>
  )
}

/** "Are you sure?" with an optional error line. */
export function Confirm({ text, action, danger, busy, error, onConfirm, onCancel }: {
  text: ReactNode; action: string; danger?: boolean; busy?: boolean; error?: string; onConfirm: () => void; onCancel: () => void
}) {
  return (
    <>
      <p className="text-[14px] text-neutral-600">{text}</p>
      {error && <p className="text-[13px] text-red-500">{error}</p>}
      <div className="flex gap-2 justify-end">
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <span className={busy ? 'opacity-50 pointer-events-none' : ''}>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>{busy ? 'Working…' : action}</Button>
        </span>
      </div>
    </>
  )
}

export const inputCls = 'w-full px-4 py-2.5 rounded-xl border border-neutral-300 text-[14px] focus:outline-none focus:border-brand-400'
