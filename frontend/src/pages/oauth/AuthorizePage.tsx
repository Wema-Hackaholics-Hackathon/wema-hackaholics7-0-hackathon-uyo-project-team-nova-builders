/**
 * "Continue with FOID" popup — /oauth/authorize?client_id=…&state=…&code_challenge=…  (opened by the SDK)
 * and /oauth/continue/:rid (reloads, and the way back from the hosted verification for new people).
 *
 *   sign in (FOID session, or email code [+ authenticator code]) → consent → only what's missing
 *   → fresh face re-match (live, first time with this business) → Allow → code back to the business page
 *   New person: name → hosted verification (same popup) → explicit "Save this to FOID" (optional) → result
 *
 * The result goes to the opener with postMessage, only to the origin the app registered.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'
import LivenessModal from '@/liveness/LivenessModal'
import { NinVerifyAction } from '@/pages/dashboard/MyIdentityPage'
import { useAuth } from '@/contexts/AuthContext'
import { api, apiErrorMessage, deviceId } from '@/lib/api'

const BRAND = '#C800DE'
const input = 'w-full border border-neutral-200 rounded-lg px-3 py-2.5 text-[14px] outline-none focus:border-[#C800DE]'
const primary = 'w-full py-3 rounded-xl text-white font-bold text-[14px] disabled:opacity-50'
const secondary = 'w-full py-2.5 rounded-xl border border-neutral-200 text-[13.5px] font-semibold text-neutral-800 hover:bg-neutral-50 disabled:opacity-50'
const grad = { background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)' }

interface View {
  id: string; status: string; test_mode: boolean; email: string | null
  app: { name: string; client_id: string }
  business: { name: string; logo_url: string | null; website?: string | null; kyb_approved: boolean }
  scopes: { scope: string; description: string }[]
}
interface Review {
  missing: string[]; rematch_required: boolean; rematch_done: boolean; already_shared: boolean
  person: { first_name: string; last_name: string; email: string }
}
interface Result { response_mode: 'web_message' | 'query'; origin?: string; redirect_url?: string; payload: Record<string, string> }
interface GuestStatus { verification_status: string; outcome: string | null; first_name: string | null; can_save_to_foid: boolean; saved_to_foid: boolean }
type Step = 'loading' | 'error' | 'choose' | 'email' | 'code' | 'mfa' | 'review' | 'guest-name' | 'guest-back' | 'done'

const store = (rid: string) => `foid_oauth_${rid}`
const AUTH_PARAMS = ['client_id', 'response_mode', 'origin', 'redirect_uri', 'scope', 'state', 'nonce', 'code_challenge', 'code_challenge_method'] as const

export default function AuthorizePage() {
  const { rid: ridParam } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { user, isAuthenticated, loading: authLoading, adoptTokens, completeMfa, refreshUser, logout } = useAuth()
  const [view, setView]       = useState<View | null>(null)
  const [step, setStep]       = useState<Step>('loading')
  const [fatal, setFatal]     = useState('')
  const [error, setError]     = useState('')
  const [busy, setBusy]       = useState(false)
  const [email, setEmail]     = useState('')
  const [code, setCode]       = useState('')
  const [mfaToken, setMfa]    = useState('')
  const [review, setReview]   = useState<Review | null>(null)
  const [liveness, setLive]   = useState<'enrol' | 'verify' | null>(null)
  const [guest, setGuest]     = useState<GuestStatus | null>(null)
  const [names, setNames]     = useState({ first_name: '', middle_name: '', last_name: '', date_of_birth: '' })
  const [doneText, setDone]   = useState('')

  const rid = view?.id ?? ridParam ?? ''
  const ticket = () => sessionStorage.getItem(store(rid)) ?? ''

  /* load the request: start it (from the SDK's URL) or read it back */
  useEffect(() => {
    void (async () => {
      try {
        if (ridParam) {
          const v = (await api.get<View>(`/oauth/requests/${ridParam}`)).data
          if (v.status !== 'pending') { setFatal('This sign-in has already finished. Start again from the app.'); setStep('error'); return }
          setView(v)
        } else {
          const body: Record<string, string> = {}
          for (const k of AUTH_PARAMS) { const v = params.get(k); if (v) body[k] = v }
          const v = (await api.post<View>('/oauth/authorize', body)).data
          setView(v)
          navigate(`/oauth/continue/${v.id}`, { replace: true })   // reload-safe, and the OAuth params leave the address bar
        }
      } catch (e) {
        setFatal(apiErrorMessage(e, 'This sign-in link is not valid.')); setStep('error')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadReview = useCallback(async () => {
    try {
      setReview((await api.get<Review>(`/oauth/requests/${rid}/review`)).data)
      setStep('review')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [rid])

  /* first screen once we know who's here */
  useEffect(() => {
    if (!view || authLoading || step !== 'loading') return
    if (ticket()) {
      void api.post<GuestStatus>(`/oauth/requests/${view.id}/guest/status`, { ticket: ticket() })
        .then(r => { setGuest(r.data); setStep('guest-back') })
        .catch(() => { sessionStorage.removeItem(store(view.id)); setStep(isAuthenticated ? 'choose' : 'email') })
    } else setStep(isAuthenticated ? 'choose' : 'email')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, authLoading])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) { setError(apiErrorMessage(e)) } finally { setBusy(false) }
  }

  /* hand the result back to the business page */
  function deliver(r: Result) {
    sessionStorage.removeItem(store(rid))
    const ok = !!r.payload.code
    if (r.response_mode === 'query' && r.redirect_url) { window.location.href = r.redirect_url; return }
    if (window.opener && r.origin) {
      window.opener.postMessage({ type: 'foid:oauth', ...r.payload }, r.origin)
      setDone(ok ? `Done — returning you to ${view?.app.name}.` : 'Cancelled — nothing was shared.')
      setStep('done')
      setTimeout(() => window.close(), 600)
    } else {
      setDone(ok ? 'Approved, but the app’s window was closed. Go back to the app and try again.' : 'Cancelled — nothing was shared.')
      setStep('done')
    }
  }

  const sendCode = () => run(async () => {
    await api.post(`/oauth/requests/${rid}/email`, { email: email.trim() })
    setCode(''); setStep('code')
  })
  const verifyCode = () => run(async () => {
    const r = (await api.post<{ account: boolean; access_token?: string; refresh_token?: string; mfa_required?: boolean; mfa_token?: string; guest_ticket?: string }>(
      `/oauth/requests/${rid}/email/verify`, { code, device_id: deviceId() })).data
    if (!r.account && r.guest_ticket) { sessionStorage.setItem(store(rid), r.guest_ticket); setStep('guest-name'); return }
    if (r.mfa_required && r.mfa_token) { setMfa(r.mfa_token); setCode(''); setStep('mfa'); return }
    await adoptTokens(r.access_token!, r.refresh_token!)
    await loadReview()
  })
  const verifyMfa = () => run(async () => {
    const r = await completeMfa(mfaToken, code)
    if (!r.ok) throw new Error(r.error)
    await loadReview()
  })
  const approve = () => run(async () => deliver((await api.post<Result>(`/oauth/requests/${rid}/approve`)).data))
  const deny = () => run(async () => deliver((await api.post<Result>(`/oauth/requests/${rid}/deny`)).data))
  const guestStart = () => run(async () => {
    const r = (await api.post<{ hosted_url: string }>(`/oauth/requests/${rid}/guest/start`, {
      ticket: ticket(), ...names, middle_name: names.middle_name || null, date_of_birth: names.date_of_birth || null })).data
    window.location.href = r.hosted_url
  })
  const guestFinish = () => run(async () => deliver((await api.post<Result>(`/oauth/requests/${rid}/guest/finish`, { ticket: ticket() })).data))
  const saveToFoid = () => run(async () => {
    const t = (await api.post<{ access_token: string; refresh_token: string }>(`/oauth/requests/${rid}/guest/save`,
      { ticket: ticket(), device_id: deviceId() })).data
    await adoptTokens(t.access_token, t.refresh_token)
    deliver((await api.post<Result>(`/oauth/requests/${rid}/guest/finish`, { ticket: ticket() })).data)
  })

  const ready = review && review.missing.length === 0 && (!review.rematch_required || review.rematch_done)

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col items-center px-4 py-5">
      <div className="w-full max-w-[440px] bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100" style={{ borderTop: `4px solid ${BRAND}` }}>
          <div className="flex items-center gap-2">
            <FoidWordmark height={15} color={BRAND} />
            <span className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wider">Sign in</span>
          </div>
          {view?.test_mode && <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">TEST</span>}
        </div>

        <div className="p-5 flex flex-col gap-4">
          {step === 'error' && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-link-unlink-m" size={32} color="#a1a1aa" />
              <p className="text-[14px] text-neutral-600">{fatal}</p>
            </div>
          )}
          {step === 'loading' && (
            <div className="flex items-center justify-center gap-2 py-10 text-neutral-400 text-[13px]">
              <RemixIcon name="ri-loader-4-line" size={18} /> Loading…
            </div>
          )}

          {view && step !== 'error' && step !== 'loading' && step !== 'done' && (
            <div className="flex items-center gap-3">
              <img src={view.business.logo_url ?? '/logo.png'} alt="" className="w-10 h-10 rounded-lg border border-neutral-100 object-contain bg-white" />
              <div className="min-w-0">
                <div className="text-[15px] font-bold text-neutral-900 truncate">{view.app.name}</div>
                <div className="text-[12px] text-neutral-500 truncate flex items-center gap-1">
                  {view.business.name}
                  {view.business.kyb_approved && !view.test_mode && <RemixIcon name="ri-verified-badge-fill" size={13} color="#16a34a" />}
                </div>
              </div>
            </div>
          )}
          {view?.test_mode && step !== 'error' && step !== 'done' && (
            <p className="text-[12px] rounded-lg bg-amber-50 border border-amber-200 text-amber-800 px-3 py-2">
              <b>Test app — not checked by FOID.</b> It only gets your real name; everything else it sees is sample data.
            </p>
          )}

          {step === 'choose' && user && (
            <>
              <p className="text-[13.5px] text-neutral-600">Continue to {view?.app.name} with your FOID?</p>
              <button className={primary} style={grad} disabled={busy} onClick={() => void loadReview()}>
                Continue as {user.firstName} {user.lastName?.[0]}.
              </button>
              <button className={secondary} onClick={() => { void logout().then(() => setStep('email')) }}>Use a different account</button>
            </>
          )}

          {step === 'email' && (
            <form className="flex flex-col gap-3" onSubmit={e => { e.preventDefault(); void sendCode() }}>
              <p className="text-[13.5px] text-neutral-600">Enter your email. We'll send a code — no password needed. New to FOID? You can still continue.</p>
              <input className={input} type="email" autoFocus placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
              <button className={primary} style={grad} disabled={busy || !email.includes('@')}>{busy ? 'Sending…' : 'Send code'}</button>
            </form>
          )}

          {(step === 'code' || step === 'mfa') && (
            <form className="flex flex-col gap-3" onSubmit={e => { e.preventDefault(); void (step === 'code' ? verifyCode() : verifyMfa()) }}>
              <p className="text-[13.5px] text-neutral-600">
                {step === 'code' ? <>Enter the 6-digit code we sent to <b>{email}</b>.</> : 'Enter the 6-digit code from your authenticator app.'}
              </p>
              <input className={`${input} tracking-[0.3em] text-center text-[16px]`} inputMode="numeric" autoComplete="one-time-code" autoFocus
                maxLength={6} placeholder="123456" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
              <button className={primary} style={grad} disabled={busy || code.length !== 6}>{busy ? 'Checking…' : 'Continue'}</button>
              {step === 'code' && <button type="button" className="text-[13px] font-semibold text-[#C800DE]" onClick={() => setStep('email')}>Use a different email</button>}
            </form>
          )}

          {step === 'review' && review && view && (
            <>
              <div>
                <p className="text-[13.5px] text-neutral-700"><b>{view.app.name}</b> wants to see:</p>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {view.scopes.map(s => (
                    <li key={s.scope} className="flex gap-2 text-[13px] text-neutral-700">
                      <RemixIcon name="ri-check-line" size={16} color={BRAND} /><span>{s.description}</span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11.5px] text-neutral-400 mt-2">They get confirmations, never your full NIN or BVN. You can revoke access any time in FOID → Consent requests.</p>
              </div>

              {review.missing.includes('liveness') && (
                <Task icon="ri-camera-lens-line" title="Set up your face check" text="A quick selfie check so FOID can confirm it's you." action="Start" onClick={() => setLive('enrol')} />
              )}
              {review.missing.includes('nin') && !review.missing.includes('liveness') && (
                <div className="rounded-xl border border-neutral-200 p-3">
                  <div className="text-[13px] font-semibold text-neutral-900 mb-1">Verify your NIN</div>
                  <NinVerifyAction user={user} onSuccess={() => { void refreshUser().then(loadReview) }} />
                </div>
              )}
              {review.missing.length === 0 && review.rematch_required && !review.rematch_done && (
                <Task icon="ri-user-smile-line" title="Confirm it's you" text={`First time sharing with ${view.business.name}: a 5-second face check.`} action="Start" onClick={() => setLive('verify')} />
              )}
              {review.rematch_required && review.rematch_done && (
                <p className="text-[12.5px] text-green-700 flex items-center gap-1.5"><RemixIcon name="ri-checkbox-circle-fill" size={15} color="#16a34a" /> Face confirmed</p>
              )}

              <button className={primary} style={grad} disabled={busy || !ready} onClick={() => void approve()}>{busy ? 'Sharing…' : 'Allow'}</button>
              <button className={secondary} disabled={busy} onClick={() => void deny()}>Cancel</button>
              <p className="text-[11.5px] text-neutral-400 text-center">Signed in as {review.person.email}</p>
            </>
          )}

          {step === 'guest-name' && (
            <form className="flex flex-col gap-3" onSubmit={e => { e.preventDefault(); void guestStart() }}>
              <p className="text-[13.5px] text-neutral-600">You don't have FOID yet — let's verify you for {view?.app.name}. Enter your name exactly as on your NIN.</p>
              <input className={input} placeholder="First name" value={names.first_name} onChange={e => setNames(n => ({ ...n, first_name: e.target.value }))} autoFocus />
              <input className={input} placeholder="Middle name (optional)" value={names.middle_name} onChange={e => setNames(n => ({ ...n, middle_name: e.target.value }))} />
              <input className={input} placeholder="Last name" value={names.last_name} onChange={e => setNames(n => ({ ...n, last_name: e.target.value }))} />
              <label className="text-[12px] text-neutral-500">Date of birth (optional)
                <input className={input} type="date" value={names.date_of_birth} onChange={e => setNames(n => ({ ...n, date_of_birth: e.target.value }))} />
              </label>
              <button className={primary} style={grad} disabled={busy || !names.first_name.trim() || !names.last_name.trim()}>{busy ? 'Starting…' : 'Continue'}</button>
              <button type="button" className={secondary} disabled={busy} onClick={() => void deny()}>Cancel</button>
            </form>
          )}

          {step === 'guest-back' && guest && (
            guest.verification_status !== 'completed' && guest.verification_status !== 'cancelled' ? (
              <>
                <p className="text-[13.5px] text-neutral-600">Your verification isn't finished yet.</p>
                <button className={primary} style={grad} onClick={() => setStep('guest-name')}>Continue verifying</button>
              </>
            ) : guest.can_save_to_foid ? (
              <>
                <div className="text-center flex flex-col items-center gap-2">
                  <RemixIcon name="ri-shield-check-fill" size={36} color={BRAND} />
                  <h1 className="text-[16px] font-bold text-neutral-900">You're verified{guest.first_name ? `, ${guest.first_name}` : ''}</h1>
                  <p className="text-[13px] text-neutral-600">Save this to FOID so you never have to repeat it — next time, any app using FOID takes seconds.</p>
                </div>
                <button className={primary} style={grad} disabled={busy} onClick={() => void saveToFoid()}>{busy ? 'Saving…' : 'Save this to FOID'}</button>
                <button className={secondary} disabled={busy} onClick={() => void guestFinish()}>No thanks, just continue</button>
                <p className="text-[11.5px] text-neutral-400 text-center">Saving creates a FOID account with this email. Set a password later with “Forgot password”.</p>
              </>
            ) : (
              <>
                <p className="text-[13.5px] text-neutral-600">{guest.saved_to_foid ? 'Saved to FOID.' : 'Verification finished.'} Continue to {view?.app.name}.</p>
                <button className={primary} style={grad} disabled={busy} onClick={() => void guestFinish()}>Continue</button>
              </>
            )
          )}

          {step === 'done' && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-checkbox-circle-fill" size={40} color={BRAND} />
              <p className="text-[14px] text-neutral-700">{doneText}</p>
            </div>
          )}

          {error && <p className="text-[12.5px] text-red-600">{error}</p>}
        </div>

        <div className="px-5 py-3 bg-neutral-50 border-t border-neutral-100 flex items-center justify-center gap-1.5 text-[11.5px] text-neutral-400">
          <RemixIcon name="ri-lock-2-line" size={13} color="#a1a1aa" /> Secured by <FoidWordmark height={11} color={BRAND} />
        </div>
      </div>

      <LivenessModal open={liveness !== null} purpose={liveness ?? 'verify'} onClose={() => setLive(null)}
        onPassed={() => { setLive(null); void refreshUser().then(loadReview) }} />
    </div>
  )
}

function Task({ icon, title, text, action, onClick }: { icon: string; title: string; text: string; action: string; onClick: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-neutral-200 p-3">
      <RemixIcon name={icon} size={22} color={BRAND} />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-semibold text-neutral-900">{title}</div>
        <div className="text-[12px] text-neutral-500">{text}</div>
      </div>
      <button onClick={onClick} className="px-3 py-1.5 rounded-full text-white text-[12.5px] font-semibold" style={grad}>{action}</button>
    </div>
  )
}
