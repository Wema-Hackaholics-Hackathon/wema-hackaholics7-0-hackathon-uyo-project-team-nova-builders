/**
 * Go live — the business enters its details and uploads documents; the owner submits;
 * a FOID admin approves (Live unlocks) or rejects with a note (fix and resubmit).
 * Backend: /business/organisations/{id}/kyb* (backend/app/routers/kyb.py).
 */
import { useCallback, useEffect, useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import { Button, PageHeader, Panel, Pill } from '@/components/ui'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'

interface Doc { id: string; type: string; filename: string; size: number; uploaded_at: string }
interface Kyb {
  status: 'not_submitted' | 'pending' | 'approved' | 'rejected'
  rc_number: string | null; tin: string | null; registered_address: string | null
  submitted_at: string | null; note: string | null; editable: boolean
  document_types: { type: string; label: string; required: boolean }[]
  documents: Doc[]
  missing: string[]
}
type Details = { rc_number: string; tin: string; registered_address: string }

const HINTS: Record<string, string> = {
  cac_certificate: 'PDF or a clear photo', cac_status: 'Issued in the last 12 months', memart: 'PDF',
  director_id: 'NIN slip, passport or driver’s licence', proof_address: 'Utility bill from the last 3 months',
  licence: 'CBN, SEC, etc. — only if you’re regulated',
}
const STEPS = ['Upload documents', 'FOID review (1–2 business days)', 'Live keys enabled']
const kb = (n: number) => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`

function Input({ label, value, onChange, disabled, className = '', placeholder }: {
  label: string; value: string; onChange: (v: string) => void; disabled: boolean; className?: string; placeholder?: string
}) {
  return (
    <label className={`flex flex-col gap-2 ${className}`}>
      <span className="text-[15px] font-semibold text-neutral-900">{label}</span>
      <input value={value} disabled={disabled} placeholder={placeholder} onChange={e => onChange(e.target.value)}
        className="px-4 py-2.5 rounded-full border border-neutral-300 text-[13.5px] text-neutral-700 focus:outline-none focus:border-brand-400 disabled:bg-neutral-50 disabled:text-neutral-500" />
    </label>
  )
}

export default function GoLivePage() {
  const { org, can, reloadOrgs, mode, setMode } = useMode()
  const [kyb, setKyb] = useState<Kyb | null>(null)
  const [details, setDetails] = useState<Details>({ rc_number: '', tin: '', registered_address: '' })
  const [busyType, setBusyType] = useState('')
  const [docErrors, setDocErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const base = org ? `/business/organisations/${org.id}/kyb` : ''

  const apply = (k: Kyb) => {
    setKyb(k)
    setDetails({ rc_number: k.rc_number ?? '', tin: k.tin ?? '', registered_address: k.registered_address ?? '' })
  }
  const load = useCallback(async () => {
    if (!base) return
    try { apply((await api.get<Kyb>(base)).data) } catch (e) { setError(apiErrorMessage(e)) }
  }, [base])
  useEffect(() => { void load() }, [load])

  if (!kyb) {
    return <div className="flex items-center gap-2 text-neutral-400 text-[13px]"><RemixIcon name="ri-loader-4-line" size={18} /> {error || 'Loading…'}</div>
  }

  const canEdit = kyb.editable && can('admin')
  const isOwner = can('owner')
  const step = kyb.status === 'approved' ? 3 : kyb.status === 'pending' ? 1 : 0
  const docOf = (t: string) => kyb.documents.find(d => d.type === t)
  const detailsMissing = (['rc_number', 'tin', 'registered_address'] as const).filter(f => !details[f].trim())
  const docsMissing = kyb.document_types.filter(d => d.required && !docOf(d.type))
  const ready = detailsMissing.length === 0 && docsMissing.length === 0

  const upload = async (type: string, file: File) => {
    setBusyType(type); setDocErrors(e => ({ ...e, [type]: '' }))
    const form = new FormData()
    form.append('type', type)
    form.append('file', file)
    try {
      await api.post(`${base}/documents`, form)
      await load()
    } catch (e) {
      setDocErrors(errs => ({ ...errs, [type]: apiErrorMessage(e, 'Upload failed') }))
    } finally { setBusyType('') }
  }
  const remove = async (doc: Doc) => {
    setBusyType(doc.type)
    try { await api.delete(`${base}/documents/${doc.id}`); await load() }
    catch (e) { setDocErrors(errs => ({ ...errs, [doc.type]: apiErrorMessage(e) })) }
    finally { setBusyType('') }
  }
  const submit = async () => {
    setSubmitting(true); setError('')
    try {
      await api.put(`${base}/details`, details)
      apply((await api.post<Kyb>(base)).data)
      await reloadOrgs()
    } catch (e) { setError(apiErrorMessage(e)) } finally { setSubmitting(false) }
  }
  const saveDetails = async () => {
    setError('')
    try { apply((await api.put<Kyb>(`${base}/details`, details)).data) } catch (e) { setError(apiErrorMessage(e)) }
  }

  return (
    <div className="pb-8 flex flex-col gap-6 max-w-[900px]">
      <PageHeader title="Go live" subtitle="Live mode works with real people and real charges. We need a few documents about your business first." />

      <ol className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {STEPS.map((s, i) => {
          const done = i < step
          return (
            <li key={s} className={`flex items-center gap-2 rounded-xl border p-3 text-[13px] font-semibold ${i <= step ? 'border-[#C800DE] bg-brand-50 text-neutral-900' : 'border-neutral-200 text-neutral-400'}`}>
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[12px] text-white ${done ? 'bg-green-600' : i === step ? 'bg-[#C800DE]' : 'bg-neutral-300'}`}>
                {done ? <RemixIcon name="ri-check-line" size={14} color="#fff" /> : i + 1}
              </span>
              {s}
            </li>
          )
        })}
      </ol>

      {kyb.status === 'pending' && (
        <p className="flex gap-2 rounded-xl bg-orange-50 border border-orange-200 p-4 text-[13px] text-orange-700">
          <RemixIcon name="ri-time-line" size={18} /> Submitted — we’re reviewing your documents. Keep building in Test mode; we’ll email the owners when it’s done.
        </p>
      )}
      {kyb.status === 'approved' && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-green-50 border border-green-200 p-4 text-[13px] text-green-700">
          <RemixIcon name="ri-checkbox-circle-line" size={18} /> Approved — Live is unlocked.
          {mode !== 'live' && <button onClick={() => setMode('live')} className="ml-auto px-4 py-1.5 rounded-full bg-green-600 text-white font-semibold">Switch to Live</button>}
        </div>
      )}
      {kyb.status === 'rejected' && (
        <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-[13px] text-red-700">
          <div className="flex gap-2 font-semibold"><RemixIcon name="ri-error-warning-line" size={18} /> We need a few changes before we can approve you</div>
          {kyb.note && <p className="mt-1 ml-6">“{kyb.note}”</p>}
          <p className="mt-1 ml-6 text-red-600/80">Update what’s needed below and submit again.</p>
        </div>
      )}
      {!can('admin') && kyb.editable && (
        <p className="text-[13px] text-neutral-500">Only owners and admins can upload documents. Ask an owner to finish this.</p>
      )}

      <Panel title="Business details">
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
          <Input label="RC number" placeholder="RC1234567" value={details.rc_number} disabled={!canEdit}
            onChange={v => setDetails(d => ({ ...d, rc_number: v }))} />
          <Input label="Tax ID (TIN)" placeholder="12345678-0001" value={details.tin} disabled={!canEdit}
            onChange={v => setDetails(d => ({ ...d, tin: v }))} />
          <Input label="Registered address" className="md:col-span-2" value={details.registered_address} disabled={!canEdit}
            onChange={v => setDetails(d => ({ ...d, registered_address: v }))} />
          {canEdit && <div><Button variant="outline" onClick={() => void saveDetails()}>Save details</Button></div>}
        </div>
      </Panel>

      <Panel title="Documents" subtitle="PDF, JPEG or PNG. Max 10 MB each. Stored encrypted — only FOID’s review team can open them.">
        {kyb.document_types.map(t => {
          const doc = docOf(t.type)
          const busy = busyType === t.type
          return (
            <div key={t.type} className="flex flex-col sm:flex-row sm:items-center gap-3 px-6 py-4 border-b border-neutral-200 last:border-0">
              <RemixIcon name={doc ? 'ri-file-check-line' : 'ri-file-upload-line'} size={22} color={doc ? '#16a34a' : '#a1a1aa'} />
              <div className="flex-1 min-w-0">
                <div className="text-[14px] font-semibold">{t.label}</div>
                <div className="text-[12px] text-neutral-500 truncate">
                  {doc ? `${doc.filename} · ${kb(doc.size)}` : HINTS[t.type]}
                </div>
                {docErrors[t.type] && <div className="text-[12px] text-red-500">{docErrors[t.type]}</div>}
              </div>
              {!t.required && !doc && <Pill tone="neutral">Optional</Pill>}
              {canEdit && (
                <div className="flex gap-2">
                  {doc && (
                    <button onClick={() => void remove(doc)} disabled={busy} aria-label={`Remove ${t.label}`}
                      className="px-3 py-2 rounded-full border border-neutral-200 hover:bg-neutral-50 disabled:opacity-40">
                      <RemixIcon name="ri-delete-bin-line" size={15} clickable />
                    </button>
                  )}
                  <label className={`px-5 py-2 rounded-full border border-neutral-200 text-[13px] font-semibold text-center ${busy ? 'opacity-40 pointer-events-none' : 'cursor-pointer hover:bg-neutral-50'}`}>
                    {busy ? 'Uploading…' : doc ? 'Replace' : 'Upload'}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void upload(t.type, f) }} />
                  </label>
                </div>
              )}
            </div>
          )
        })}
      </Panel>

      {kyb.editable && (
        <div className="flex flex-col gap-2">
          {error && <p className="text-[13px] text-red-500">{error}</p>}
          {isOwner ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className={!ready || submitting ? 'opacity-50 pointer-events-none' : ''}>
                <Button icon="ri-send-plane-line" onClick={() => void submit()}>
                  {submitting ? 'Submitting…' : kyb.status === 'rejected' ? 'Submit again' : 'Submit for review'}
                </Button>
              </span>
              {!ready && (
                <span className="text-[12.5px] text-neutral-500">
                  Still needed: {[...detailsMissing.map(f => ({ rc_number: 'RC number', tin: 'TIN', registered_address: 'address' })[f]),
                    ...docsMissing.map(d => d.label)].join(', ')}
                </span>
              )}
            </div>
          ) : (
            <p className="text-[12.5px] text-neutral-500">Only an owner can submit — by submitting they confirm the documents are genuine.</p>
          )}
        </div>
      )}
    </div>
  )
}
