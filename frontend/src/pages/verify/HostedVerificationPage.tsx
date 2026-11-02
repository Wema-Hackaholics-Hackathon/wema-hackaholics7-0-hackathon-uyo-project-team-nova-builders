/**
 * FOID-hosted verification page — /verify/:token
 *
 * Businesses create a verification with the Open API and send people here
 * (redirect, or embedded in their app with /foid-verify.js). No FOID account
 * is needed. Flow: consent → (optional "use my FOID identity") → each requested
 * step (NIN, BVN, liveness) → finish → postMessage to the embedding page and/or
 * redirect to the business's return_url.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import FoidWordmark from '@/components/FoidWordmark'
import LivenessStage, { FAILURES, type LivenessResult, type StartedSession } from '@/liveness/LivenessStage'
import RemixIcon from '@/components/RemixIcon'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import type { HostedSession, HostedStep, HostedStepResult } from '@/types/foid'

const STEP_META: Record<string, { label: string; icon: string; hint: string }> = {
  nin:      { label: 'NIN',             icon: 'ri-shield-user-line', hint: 'Your 11-digit National Identification Number' },
  bvn:      { label: 'BVN',             icon: 'ri-bank-line',        hint: 'Your 11-digit Bank Verification Number' },
  liveness: { label: 'Liveness check',  icon: 'ri-camera-line',      hint: 'A quick camera check that you are present' },
  reverify: { label: 'Face check',      icon: 'ri-camera-line',      hint: 'Confirm it is still you' },
}

const REASONS: Record<string, string> = {
  not_found: "We couldn't find that number. Check it and try again.",
  name_mismatch: "The name on record doesn't match the name this business has for you.",
  dob_mismatch: "The date of birth on record doesn't match.",
  document_unreadable: "We couldn't read the NIN on that image. Use a sharper, well-lit photo.",
  unsupported_document: 'Upload an NIN slip or NIMC card.',
  low_ocr_confidence: 'The image was hard to read — it will be reviewed.',
  face_mismatch: "That face didn't match the one on file.",
  provider_unavailable: 'Verification is temporarily unavailable. Try again shortly.',
  ocr_unavailable: 'Document scanning is unavailable — enter your NIN instead.',
  ...FAILURES,
  face_record_rejected: 'The liveness result could not be accepted. Please try again.',
  no_face_captured: 'No face was captured. Face the camera in good light and try again.',
}

function detail(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { error?: { message?: string }; detail?: unknown } } })?.response?.data
  if (d?.error?.message) return d.error.message
  return typeof d?.detail === 'string' ? d.detail : fallback
}

const embedded = typeof window !== 'undefined' && window.parent !== window

function notifyParent(session: HostedSession) {
  if (!embedded) return
  window.parent.postMessage({
    source: 'foid',
    type: session.status === 'completed' ? 'verification.completed' : 'verification.cancelled',
    verification_id: session.id,
    status: session.status,
    outcome: session.outcome,
  }, '*')
}

/* ── Number entry (NIN / BVN) with optional document scan ───────────── */
function NumberStep({ step, base, onDone }: { step: HostedStep; base: string; onDone: (r: HostedStepResult) => void }) {
  const [mode, setMode]       = useState<'number' | 'document'>('number')
  const [value, setValue]     = useState('')
  const [file, setFile]       = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const allowDocument = step.type === 'nin'

  async function submit() {
    setError('')
    setLoading(true)
    try {
      let r: HostedStepResult
      if (mode === 'document' && file) {
        const form = new FormData()
        form.append('file', file)
        r = (await api.post<HostedStepResult>(`${base}/nin-document`, form)).data
      } else {
        r = (await api.post<HostedStepResult>(`${base}/${step.type}`, { number: value.replace(/\D/g, '') })).data
      }
      onDone(r)
    } catch (e) {
      setError(detail(e, 'Something went wrong. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  const digits = value.replace(/\D/g, '')
  const ready = mode === 'number' ? digits.length === 11 : !!file

  return (
    <div className="flex flex-col gap-3">
      {allowDocument && (
        <div className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-neutral-100 text-[13px] font-semibold">
          {(['number', 'document'] as const).map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setError('') }}
              className={['py-2 rounded-md transition-colors', mode === m ? 'bg-white text-neutral-900 shadow-sm' : 'text-neutral-500'].join(' ')}
            >
              {m === 'number' ? 'Enter number' : 'Scan NIN slip / card'}
            </button>
          ))}
        </div>
      )}
      {mode === 'number' ? (
        <input
          inputMode="numeric"
          autoComplete="off"
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder={STEP_META[step.type]?.hint}
          className="w-full border border-neutral-200 rounded-lg px-3 py-2.5 text-[15px] tracking-wider outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
          onKeyDown={e => { if (e.key === 'Enter' && ready) void submit() }}
        />
      ) : (
        <label className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-neutral-200 rounded-xl py-6 px-3 text-center cursor-pointer hover:border-brand-400">
          <RemixIcon name="ri-image-add-line" size={26} color="#a1a1aa" />
          <span className="text-[13px] text-neutral-600">{file ? file.name : 'Take a photo or upload your NIN slip / NIMC card'}</span>
          <span className="text-[11.5px] text-neutral-400">We only read your NIN from it</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            className="hidden"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
      )}
      {error && <p className="text-[12.5px] text-red-500">{error}</p>}
      <button
        onClick={() => void submit()}
        disabled={!ready || loading}
        className="flex items-center justify-center gap-2 py-2.5 rounded-lg bg-brand-500 text-white text-[14px] font-semibold hover:bg-brand-600 transition-colors disabled:opacity-50"
      >
        {loading ? <><RemixIcon name="ri-loader-4-line" size={16} color="#fff" /> Verifying…</> : 'Continue'}
      </button>
      <p className="text-[11.5px] text-neutral-400 text-center">{step.attempts_left} attempt{step.attempts_left === 1 ? '' : 's'} left</p>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
export default function HostedVerificationPage() {
  const { token = '' } = useParams()
  const { isAuthenticated, user } = useAuth()
  const base = `/hosted/sessions/${token}`

  const [session, setSession] = useState<HostedSession | null>(null)
  const [fatal, setFatal]     = useState('')
  const [busy, setBusy]       = useState(false)
  const [notice, setNotice]   = useState('')

  const load = useCallback(async () => {
    try {
      setSession((await api.get<HostedSession>(base)).data)
    } catch (e) {
      setFatal(detail(e, 'This verification link is invalid or has expired.'))
    }
  }, [base])

  useEffect(() => { void load() }, [load])

  const closed = session?.status === 'completed' || session?.status === 'cancelled' || session?.status === 'expired'
  useEffect(() => {
    if (!session || !closed) return
    notifyParent(session)
    if (!embedded && session.redirect_url) {
      const t = setTimeout(() => { window.location.href = session.redirect_url! }, 2500)
      return () => clearTimeout(t)
    }
  }, [session, closed])

  async function act(path: string, body?: unknown) {
    setBusy(true)
    setNotice('')
    try {
      const r = (await api.post<HostedSession & { reused?: string[] }>(`${base}${path}`, body)).data
      setSession(r)
      if (r.reused) setNotice(r.reused.length ? 'We used your verified FOID identity — fewer steps for you.' : 'Nothing could be reused — please complete the steps below.')
    } catch (e) {
      setNotice(detail(e, 'Something went wrong. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const steps = session?.steps ?? []
  const current = steps.find(s => s.status !== 'passed' && s.attempts_left > 0)
  const allDone = steps.length > 0 && !current

  const brand = session?.business.brand_color ?? '#C800DE'

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-[440px] bg-white border border-neutral-200 rounded-2xl shadow-sm overflow-hidden">

        {/* ── Business header ── */}
        <div className="px-5 py-4 border-b border-neutral-100 flex items-center gap-3" style={{ borderTop: `4px solid ${brand}` }}>
          {session?.business.logo_url
            ? <img src={session.business.logo_url} alt="" className="w-9 h-9 rounded-lg object-cover border border-neutral-100" />
            : <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold" style={{ background: brand }}>
                {session?.business.name.charAt(0) ?? '·'}
              </div>}
          <div className="min-w-0">
            <div className="text-[15px] font-bold text-neutral-900 truncate">{session?.business.name ?? 'Identity verification'}</div>
            <div className="text-[12px] text-neutral-400">Identity verification</div>
          </div>
          {session?.env === 'test' && (
            <span className="ml-auto text-[11px] font-bold uppercase tracking-wide px-2 py-1 rounded-md bg-amber-100 text-amber-700">Sandbox</span>
          )}
        </div>

        <div className="p-5 flex flex-col gap-4">
          {fatal && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-link-unlink-m" size={32} color="#a1a1aa" />
              <p className="text-[14px] text-neutral-600">{fatal}</p>
            </div>
          )}

          {!fatal && !session && (
            <div className="flex items-center justify-center gap-2 py-10 text-neutral-400 text-[13px]">
              <RemixIcon name="ri-loader-4-line" size={18} /> Loading…
            </div>
          )}

          {/* ── Consent ── */}
          {session && session.status === 'pending' && (
            <>
              <div>
                <h1 className="text-[18px] font-bold text-neutral-900">{session.business.name} wants to verify your identity</h1>
                <p className="text-[13px] text-neutral-500 mt-1">Purpose: {session.purpose}</p>
              </div>
              <div className="rounded-xl bg-neutral-50 border border-neutral-200 p-4 flex flex-col gap-2.5">
                <div className="text-[12px] font-semibold text-neutral-500 uppercase tracking-wide">They will be able to see</div>
                {session.scopes.map(s => (
                  <div key={s.scope} className="flex items-start gap-2 text-[13px] text-neutral-700">
                    <RemixIcon name="ri-check-line" size={16} color={brand} />
                    <span>{s.description}</span>
                  </div>
                ))}
              </div>
              <p className="text-[12px] text-neutral-500 leading-relaxed">
                FOID runs these checks for {session.business.name}. You can withdraw this permission at any time
                from <b>Connected apps</b> in a FOID account — {session.business.name} then stops receiving your data.
              </p>
              {notice && <p className="text-[12.5px] text-red-500">{notice}</p>}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => void act('/consent', { accept: false })}
                  disabled={busy}
                  className="py-2.5 rounded-lg border border-neutral-200 text-[14px] font-semibold text-neutral-700 hover:bg-neutral-50"
                >
                  Decline
                </button>
                <button
                  onClick={() => void act('/consent', { accept: true })}
                  disabled={busy}
                  className="py-2.5 rounded-lg bg-brand-500 text-white text-[14px] font-semibold hover:bg-brand-600 disabled:opacity-60"
                >
                  I agree
                </button>
              </div>
            </>
          )}

          {/* ── Steps ── */}
          {session && session.status === 'in_progress' && (
            <>
              <ol className="flex flex-col gap-2">
                {steps.map(s => (
                  <li key={s.type} className="flex items-center gap-3 text-[13.5px]">
                    <span className={[
                      'w-7 h-7 rounded-full flex items-center justify-center shrink-0',
                      s.status === 'passed' ? 'bg-brand-500' : s === current ? 'bg-brand-100' : 'bg-neutral-100',
                    ].join(' ')}>
                      <RemixIcon
                        name={s.status === 'passed' ? 'ri-check-line' : STEP_META[s.type]?.icon ?? 'ri-checkbox-blank-circle-line'}
                        size={15}
                        color={s.status === 'passed' ? '#fff' : s === current ? '#C800DE' : '#a1a1aa'}
                      />
                    </span>
                    <span className={s === current ? 'font-semibold text-neutral-900' : 'text-neutral-500'}>
                      {STEP_META[s.type]?.label ?? s.type}
                    </span>
                    {s.source === 'foid_credential' && <span className="ml-auto text-[11px] text-brand-600 font-semibold">From FOID</span>}
                    {s.status !== 'passed' && s.attempts_left === 0 && <span className="ml-auto text-[11px] text-red-500 font-semibold">Not verified</span>}
                  </li>
                ))}
              </ol>

              {isAuthenticated && !session.reused_foid_credential && steps.some(s => s.status === 'pending') && (
                <button
                  onClick={() => void act('/share-foid')}
                  disabled={busy}
                  className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-brand-200 bg-brand-50 text-brand-700 text-[13.5px] font-semibold hover:bg-brand-100"
                >
                  <RemixIcon name="ri-shield-check-line" size={16} color="#a21caf" />
                  Use my verified FOID identity{user ? ` (${user.firstName})` : ''}
                </button>
              )}
              {notice && <p className="text-[12.5px] text-neutral-600">{notice}</p>}

              {current && (
                <div className="border-t border-neutral-100 pt-4">
                  <div className="text-[15px] font-bold text-neutral-900 mb-1">{STEP_META[current.type]?.label}</div>
                  <div className="text-[12.5px] text-neutral-500 mb-3">{STEP_META[current.type]?.hint}</div>
                  {current.status !== 'pending' && current.reasons.length > 0 && (
                    <p className="text-[12.5px] text-red-500 mb-3">
                      {current.reasons.map(x => REASONS[x] ?? 'Verification failed.').join(' ')}
                    </p>
                  )}
                  {current.type === 'liveness' || current.type === 'reverify' ? (
                    <LivenessStage
                      key={`${current.type}-${current.attempts_left}`}
                      start={async () => (await api.post<StartedSession>(`${base}/liveness/start`)).data}
                      complete={async sid => (await api.post<LivenessResult>(`${base}/liveness/${sid}/complete`)).data}
                      onFinished={() => void load()}
                    />
                  ) : (
                    <NumberStep key={`${current.type}-${current.attempts_left}`} step={current} base={base} onDone={() => void load()} />
                  )}
                </div>
              )}

              {allDone && (
                <button
                  onClick={() => void act('/finish')}
                  disabled={busy}
                  className="py-2.5 rounded-lg bg-brand-500 text-white text-[14px] font-semibold hover:bg-brand-600 disabled:opacity-60"
                >
                  {busy ? 'Finishing…' : `Finish and return to ${session.business.name}`}
                </button>
              )}
            </>
          )}

          {/* ── Done ── */}
          {session && closed && (
            <div className="flex flex-col items-center text-center gap-2 py-6">
              <RemixIcon
                name={session.status === 'completed' ? 'ri-checkbox-circle-fill' : 'ri-close-circle-line'}
                size={40}
                color={session.status === 'completed' ? '#C800DE' : '#a1a1aa'}
              />
              <h2 className="text-[17px] font-bold text-neutral-900">
                {session.status === 'completed' ? 'All done' : session.status === 'expired' ? 'This link has expired' : 'Verification cancelled'}
              </h2>
              <p className="text-[13px] text-neutral-500">
                {session.status === 'completed'
                  ? `${session.business.name} will be notified of the result.`
                  : `Nothing was shared with ${session.business.name}.`}
                {!embedded && session.redirect_url ? ' Taking you back…' : ''}
              </p>
            </div>
          )}
        </div>

        {/* ── FOID footer branding ── */}
        <div className="px-5 py-3 bg-neutral-50 border-t border-neutral-100 flex items-center justify-center gap-1.5 text-[11.5px] text-neutral-400">
          <RemixIcon name="ri-lock-2-line" size={13} color="#a1a1aa" />
          Secured by <FoidWordmark height={11} color="#C800DE" />
        </div>
      </div>
    </div>
  )
}
