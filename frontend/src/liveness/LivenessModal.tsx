/**
 * Liveness check as a FOID-branded popup, for a signed-in user.
 *
 *   consent (enrolment) → choose device
 *     ├─ "Use this device"     → LivenessStage (camera here)
 *     └─ "Continue on my phone" → QR code + link (single use, 10 min) → this popup
 *                                  waits and updates when the phone finishes
 */
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'
import { api, apiErrorMessage } from '@/lib/api'
import LivenessStage, { type LivenessResult, type StartedSession } from './LivenessStage'

const BRAND = '#C800DE'
type Purpose = 'enrol' | 'verify'
type View = 'consent' | 'choose' | 'here' | 'phone' | 'done'

interface Handoff { handoff_id: string; url: string; expires_at: number; seconds_left: number }
interface HandoffStatus { status: string; seconds_left: number; result: LivenessResult | null }

function mmss(s: number) { return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }

export default function LivenessModal({
  open,
  purpose = 'enrol',
  onClose,
  onPassed,
}: {
  open: boolean
  purpose?: Purpose
  onClose: () => void
  onPassed: (result: LivenessResult) => void
}) {
  const [view, setView]         = useState<View>(purpose === 'enrol' ? 'consent' : 'choose')
  const [consent, setConsent]   = useState(false)
  const [handoff, setHandoff]   = useState<Handoff | null>(null)
  const [qr, setQr]             = useState('')
  const [left, setLeft]         = useState(0)
  const [phoneState, setPhoneState] = useState('pending')
  const [error, setError]       = useState('')
  const [copied, setCopied]     = useState(false)
  const [final, setFinal]       = useState<LivenessResult | null>(null)
  const handoffRef = useRef<Handoff | null>(null)

  // reset every time it opens
  useEffect(() => {
    if (!open) return
    setView(purpose === 'enrol' ? 'consent' : 'choose')
    setConsent(false); setHandoff(null); setQr(''); setError(''); setFinal(null); setPhoneState('pending')
  }, [open, purpose])

  // Esc closes
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // phone handoff: countdown + poll until the phone finishes or the link expires
  useEffect(() => {
    if (view !== 'phone' || !handoff) return
    const tick = setInterval(() => setLeft(Math.max(0, Math.round(handoff.expires_at - Date.now() / 1000))), 1000)
    const poll = setInterval(async () => {
      try {
        const s = (await api.get<HandoffStatus>(`/auth/me/liveness/handoff/${handoff.handoff_id}`)).data
        setPhoneState(s.status)
        if (s.status === 'completed' && s.result?.passed) {
          handoffRef.current = null
          setFinal(s.result)
          setView('done')
          onPassed(s.result)
        }
      } catch { /* keep polling; the countdown still runs */ }
    }, 2000)
    return () => { clearInterval(tick); clearInterval(poll) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, handoff])

  async function startHandoff() {
    setError('')
    try {
      const h = (await api.post<Handoff>('/auth/me/liveness/handoff', { purpose, consent })).data
      handoffRef.current = h
      setHandoff(h)
      setLeft(h.seconds_left)
      setPhoneState('pending')
      setQr(await QRCode.toDataURL(h.url, { margin: 1, width: 220, color: { dark: '#18181b', light: '#ffffff' } }))
      setView('phone')
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not create a link for your phone.'))
    }
  }

  function close() {
    const h = handoffRef.current
    if (h) void api.delete(`/auth/me/liveness/handoff/${h.handoff_id}`).catch(() => {})   // kill the open link
    handoffRef.current = null
    onClose()
  }

  async function copyLink() {
    if (!handoff) return
    await navigator.clipboard.writeText(handoff.url).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (!open) return null

  const startHere = async (): Promise<StartedSession> =>
    (await api.post<StartedSession>('/auth/me/liveness/start', { purpose, consent })).data
  const completeHere = async (sid: string): Promise<LivenessResult> =>
    (await api.post<LivenessResult>(`/auth/me/liveness/${sid}/complete`)).data

  const expired = view === 'phone' && (left <= 0 || phoneState === 'expired' || phoneState === 'cancelled')

  return (
    <div className="fixed inset-0 z-[100] flex items-stretch sm:items-center justify-center bg-black/50 sm:p-4" role="dialog" aria-modal="true"
      onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
      <div className="relative w-full sm:max-w-[480px] bg-white sm:rounded-2xl shadow-2xl flex flex-col max-h-full overflow-y-auto">
        {/* header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <FoidWordmark height={15} color={BRAND} />
            <span className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wider">
              {purpose === 'enrol' ? 'Liveness check' : 'Confirm it’s you'}
            </span>
          </div>
          <button onClick={close} aria-label="Close" className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-neutral-100">
            <RemixIcon name="ri-close-line" size={20} color="#71717a" />
          </button>
        </div>

        <div className="p-5 flex flex-col gap-4">
          {view === 'consent' && (
            <>
              <div>
                <h2 className="text-[18px] font-bold text-neutral-900">Prove you’re really you</h2>
                <p className="text-[13px] text-neutral-500 mt-1">
                  You’ll be asked to do a few quick moves — turn your head, open your mouth — in front of your camera.
                  It takes about 20 seconds.
                </p>
              </div>
              <ul className="flex flex-col gap-2 text-[13px] text-neutral-700">
                {['Find good, even light on your face', 'Remove sunglasses or hats', 'Make sure only you are in view'].map(t => (
                  <li key={t} className="flex items-center gap-2">
                    <RemixIcon name="ri-check-line" size={15} color={BRAND} /> {t}
                  </li>
                ))}
              </ul>
              <label className="flex items-start gap-2 text-[12.5px] text-neutral-600 cursor-pointer rounded-xl bg-neutral-50 border border-neutral-200 p-3">
                <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5 accent-[#C800DE]" />
                <span>I consent to FOID processing my face to verify my identity. An encrypted face template is
                  stored, and I can delete it at any time from Profile Settings.</span>
              </label>
              <button disabled={!consent} onClick={() => setView('choose')}
                className="py-3 rounded-xl text-white text-[14px] font-bold disabled:opacity-50 hover:opacity-90" style={{ background: BRAND }}>
                Continue
              </button>
            </>
          )}

          {view === 'choose' && (
            <>
              <h2 className="text-[17px] font-bold text-neutral-900">Which camera do you want to use?</h2>
              <button onClick={() => setView('here')}
                className="flex items-center gap-3 p-4 rounded-xl border border-neutral-200 hover:border-[#C800DE] hover:bg-[#fdf4ff] text-left transition-colors">
                <span className="w-10 h-10 rounded-full bg-[#fae8ff] flex items-center justify-center shrink-0">
                  <RemixIcon name="ri-camera-line" size={20} color={BRAND} />
                </span>
                <span>
                  <span className="block text-[14px] font-semibold text-neutral-900">Use this device</span>
                  <span className="block text-[12px] text-neutral-500">Use the camera on this computer or phone</span>
                </span>
              </button>
              <button onClick={() => void startHandoff()}
                className="flex items-center gap-3 p-4 rounded-xl border border-neutral-200 hover:border-[#C800DE] hover:bg-[#fdf4ff] text-left transition-colors">
                <span className="w-10 h-10 rounded-full bg-[#fae8ff] flex items-center justify-center shrink-0">
                  <RemixIcon name="ri-smartphone-line" size={20} color={BRAND} />
                </span>
                <span>
                  <span className="block text-[14px] font-semibold text-neutral-900">Continue on my phone</span>
                  <span className="block text-[12px] text-neutral-500">Scan a QR code — no need to log in on your phone</span>
                </span>
              </button>
              {error && <p className="text-[12.5px] text-red-500">{error}</p>}
            </>
          )}

          {view === 'here' && (
            <LivenessStage
              start={startHere}
              complete={completeHere}
              onFinished={res => { if (res.passed) { setFinal(res); onPassed(res) } }}
            />
          )}

          {view === 'phone' && handoff && (
            <div className="flex flex-col items-center text-center gap-3">
              {!expired ? (
                <>
                  <h2 className="text-[17px] font-bold text-neutral-900">Scan with your phone’s camera</h2>
                  <div className="p-3 rounded-2xl border-2" style={{ borderColor: BRAND }}>
                    {qr && <img src={qr} alt="QR code to continue on your phone" width={200} height={200} />}
                  </div>
                  <div className="flex items-center gap-2 text-[13px] text-neutral-600">
                    {phoneState === 'in_progress'
                      ? <><RemixIcon name="ri-loader-4-line" size={15} color={BRAND} /> Check in progress on your phone…</>
                      : <><RemixIcon name="ri-time-line" size={15} color="#71717a" /> Waiting for your phone · link expires in <b>{mmss(left)}</b></>}
                  </div>
                  <div className="w-full flex items-center gap-2 rounded-xl bg-neutral-50 border border-neutral-200 p-2">
                    <span className="flex-1 truncate text-[12px] text-neutral-500 text-left">{handoff.url}</span>
                    <button onClick={() => void copyLink()}
                      className="shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white" style={{ background: BRAND }}>
                      {copied ? 'Copied' : 'Copy link'}
                    </button>
                  </div>
                  <p className="text-[11.5px] text-neutral-400">
                    The link works once and only for the next 10 minutes. Don’t share it — whoever opens it can do the check for your account.
                  </p>
                </>
              ) : (
                <>
                  <RemixIcon name="ri-time-line" size={34} color="#a1a1aa" />
                  <h2 className="text-[16px] font-bold text-neutral-900">This link has expired</h2>
                  <p className="text-[13px] text-neutral-500">Links last 10 minutes and work once. Create a new one to continue.</p>
                  <button onClick={() => void startHandoff()}
                    className="px-5 py-2.5 rounded-xl text-white text-[13px] font-bold" style={{ background: BRAND }}>
                    Create a new link
                  </button>
                </>
              )}
              <button onClick={() => { const h = handoffRef.current; if (h) void api.delete(`/auth/me/liveness/handoff/${h.handoff_id}`).catch(() => {}); handoffRef.current = null; setView('choose') }}
                className="text-[12.5px] font-semibold text-neutral-500 hover:text-neutral-800">
                Use a different option
              </button>
            </div>
          )}

          {view === 'done' && final && (
            <div className="flex flex-col items-center text-center gap-2 py-6">
              <RemixIcon name="ri-checkbox-circle-fill" size={40} color={BRAND} />
              <h2 className="text-[17px] font-bold text-neutral-900">Liveness confirmed</h2>
              <p className="text-[13px] text-neutral-500">{final.message}</p>
            </div>
          )}

          {(view === 'done' || final) && (
            <button onClick={close} className="py-3 rounded-xl text-white text-[14px] font-bold hover:opacity-90" style={{ background: BRAND }}>
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
