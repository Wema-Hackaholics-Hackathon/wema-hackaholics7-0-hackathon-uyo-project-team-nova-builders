import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import RemixIcon from '@/components/RemixIcon'
import { useCredential } from '@/contexts/CredentialContext'
import { useAuth } from '@/contexts/AuthContext'
import { api, BASE_URL, getAccessToken } from '@/lib/api'
import type { ConnectedBank, CredentialClaims } from '@/types/foid'

/* ── Trust score ────────────────────────────────────────────────────── */
function computeTrustScore(
  claims: CredentialClaims,
  livenessVerified: boolean,
): number {
  let score = 0
  if (claims.identity_verified)                    score += 25  // NIN
  if (claims.bvn_validated)                        score += 25  // BVN
  if (livenessVerified)                            score += 20  // Liveness
  if (claims.account_stability === 'stable')       score += 15
  if (claims.repayment_reliability === 'reliable') score += 15
  return score
}

/* ── Trust ring SVG ─────────────────────────────────────────────────── */
function TrustRing({ pct }: { pct: number }) {
  const r    = 42
  const circ = 2 * Math.PI * r
  const fill = (pct / 100) * circ
  return (
    <div className="relative w-[100px] h-[100px] shrink-0">
      <svg width="100" height="100" viewBox="0 0 100 100" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="#f5d0fe" strokeWidth="8" />
        <circle
          cx="50" cy="50" r={r}
          fill="none"
          stroke="url(#tGrad)"
          strokeWidth="8"
          strokeDasharray={`${fill} ${circ}`}
          strokeLinecap="round"
        />
        <defs>
          <linearGradient id="tGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor="#e879f9" />
            <stop offset="100%" stopColor="#C800DE" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="text-[18px] font-extrabold text-neutral-900">{pct}%</span>
        <span className="text-[10px] text-neutral-400 mt-0.5">Trust</span>
      </div>
    </div>
  )
}

/* ── Step action panel (BVN / Phone input or Liveness) ──────────────── */
function StepAction({
  type,
  onSuccess,
}: {
  type: 'bvn' | 'phone' | 'liveness'
  onSuccess: () => void
}) {
  const [value, setValue]   = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  if (type === 'liveness') {
    return (
      <div className="mt-3 p-4 rounded-xl bg-neutral-50 border border-neutral-200 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-[13px] text-neutral-600">
          <RemixIcon name="ri-camera-line" size={16} color="#a1a1aa" />
          <span>Allow camera access, look at the camera and blink twice</span>
        </div>
        <button
          onClick={() => {
            setLoading(true)
            // Mocked liveness: 2-second simulated check
            setTimeout(() => { setLoading(false); onSuccess() }, 2000)
          }}
          disabled={loading}
          className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-brand-500 text-white text-[13px] font-semibold hover:bg-brand-600 transition-colors disabled:opacity-60"
        >
          {loading
            ? <><RemixIcon name="ri-loader-4-line" size={15} color="#fff" /> Checking…</>
            : <><RemixIcon name="ri-camera-line" size={15} color="#fff" /> Start liveness check</>
          }
        </button>
      </div>
    )
  }

  const isPhone  = type === 'phone'
  const label    = isPhone ? 'Phone number' : 'BVN'
  const hint     = isPhone ? 'e.g. 08012345678 or +2348012345678' : '11-digit Bank Verification Number'
  const endpoint = isPhone ? '/auth/me/phone' : '/auth/me/bvn'
  const field    = isPhone ? 'phone' : 'bvn'

  async function handleSubmit() {
    setError('')
    setLoading(true)
    try {
      await api.patch(endpoint, { [field]: value.trim() })
      onSuccess()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Submission failed. Please try again.'
      setError(typeof msg === 'string' ? msg : 'Invalid input.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-3 p-4 rounded-xl bg-neutral-50 border border-neutral-200 flex flex-col gap-3">
      <label className="text-[12px] font-semibold text-neutral-500 uppercase tracking-wide">{label}</label>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder={hint}
        className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-[14px] outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
        onKeyDown={e => { if (e.key === 'Enter') void handleSubmit() }}
      />
      {error && <p className="text-[12px] text-red-500">{error}</p>}
      <button
        onClick={() => void handleSubmit()}
        disabled={loading || value.trim().length === 0}
        className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-brand-500 text-white text-[13px] font-semibold hover:bg-brand-600 transition-colors disabled:opacity-60"
      >
        {loading
          ? <><RemixIcon name="ri-loader-4-line" size={15} color="#fff" /> Verifying…</>
          : 'Verify'
        }
      </button>
    </div>
  )
}

/* ── State meta ─────────────────────────────────────────────────────── */
const STATE_META: Record<string, { label: string; color: string; bg: string }> = {
  active:       { label: 'Fully verified · Tier 2', color: '#a21caf', bg: '#fae8ff' },
  under_review: { label: 'Under Review · Tier 2',   color: '#a16207', bg: '#fef9c3' },
  downgraded:   { label: 'Downgraded · Tier 1',     color: '#c2410c', bg: '#fff7ed' },
  revoked:      { label: 'Revoked',                 color: '#dc2626', bg: '#fee2e2' },
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
export default function MyIdentityPage() {
  const navigate = useNavigate()
  const { credential } = useCredential()
  const { user, refreshUser } = useAuth()
  const stateMeta = STATE_META[credential.state] ?? STATE_META['active']

  const [banks, setBanks]               = useState<ConnectedBank[]>([])
  const [livenessVerified, setLiveness] = useState(false)
  const [activeStep, setActiveStep]     = useState<string | null>(null)
  const [downloading, setDownloading]   = useState(false)

  useEffect(() => {
    void api.get<ConnectedBank[]>('/banks/connected').then(r => setBanks(r.data)).catch(() => {})
  }, [])

  /* ── Verification steps — driven by real user + credential data ───── */
  const emailDone      = !!user?.email
  const ninDone        = !!user?.nin
  const bvnDone        = !!user?.bvn
  const phoneVerified  = !!user?.phone

  type StepId = 'email' | 'nin' | 'bvn' | 'liveness' | 'phone'
  const steps: { id: StepId; label: string; icon: string; done: boolean }[] = [
    { id: 'email',    label: 'Email',    icon: 'ri-mail-line',        done: emailDone        },
    { id: 'nin',      label: 'NIN',      icon: 'ri-shield-user-line', done: ninDone          },
    { id: 'bvn',      label: 'BVN',      icon: 'ri-bank-line',        done: bvnDone          },
    { id: 'liveness', label: 'Liveness', icon: 'ri-camera-line',      done: livenessVerified },
    { id: 'phone',    label: 'Phone',    icon: 'ri-smartphone-line',  done: phoneVerified    },
  ]

  const allDone   = steps.every(s => s.done)
  const doneCount = steps.filter(s => s.done).length

  /* ── Trust score ─────────────────────────────────────────────────── */
  const trustPct = computeTrustScore(credential.claims, livenessVerified)

  /* ── Download PDF from backend ───────────────────────────────────── */
  async function handleDownload() {
    setDownloading(true)
    try {
      const token = getAccessToken()
      const res = await fetch(`${BASE_URL}/api/v1/auth/me/identity-summary`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = 'FOID_Identity_Summary.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // silently ignore — user will see the button re-enable
    } finally {
      setDownloading(false)
    }
  }

  /* ── Banks: show max 2, with "View all" ──────────────────────────── */
  const displayBanks = banks.slice(0, 2)
  const extraBanks   = banks.length - 2

  function formatLinkedDate(iso: string | null): string {
    if (!iso) return ''
    return 'Linked ' + new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">My Identity</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">Your verified digital identity, generated once and reusable everywhere</p>
        </div>
        <button
          onClick={() => void handleDownload()}
          disabled={downloading}
          className="flex items-center gap-2 px-5 py-2.5 border border-neutral-200 rounded-full font-semibold text-[14px] text-neutral-800 bg-white hover:bg-neutral-50 transition-colors shrink-0 w-full md:w-auto justify-center disabled:opacity-60"
        >
          {downloading
            ? <><RemixIcon name="ri-loader-4-line" size={18} /> Preparing…</>
            : <><RemixIcon name="ri-download-2-line" size={18} /> Download Identity Summary</>
          }
        </button>
      </div>

      {/* ── Hero card ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl pl-6 md:pl-9 pr-6 md:pr-[54px] py-6 md:py-10 flex flex-col md:flex-row items-center md:items-start gap-6 md:gap-7">
        {/* Avatar — initials fallback */}
        <div className="w-[70px] h-[70px] md:w-[86px] md:h-[86px] rounded-full bg-brand-100 border-[3.5px] border-brand-400 flex items-center justify-center shrink-0">
          <span className="text-[26px] md:text-[30px] font-extrabold text-brand-600 leading-none select-none">
            {user ? `${user.firstName.charAt(0)}${user.lastName.charAt(0)}` : '?'}
          </span>
        </div>

        {/* Name + badge */}
        <div className="text-center md:text-left">
          <div className="text-[20px] md:text-[22px] font-bold text-neutral-900 mb-2">
            {user ? `${user.firstName} ${user.lastName}` : '…'}
          </div>
          <span
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[13px] font-semibold"
            style={{ background: stateMeta.bg, color: stateMeta.color }}
          >
            {stateMeta.label}
          </span>
          <div className="mt-2 text-[12px] text-neutral-400">
            {doneCount}/{steps.length} verification steps complete
          </div>
        </div>

        {/* Trust ring — pushed right */}
        <div className="flex items-center gap-5 md:ml-auto">
          <TrustRing pct={trustPct} />
          <div>
            <div className="text-[11px] text-neutral-400 mb-1">Trust Score</div>
            <div className="text-[20px] md:text-[22px] font-extrabold text-neutral-900 leading-none">{trustPct}/100</div>
            <div className="text-[12px] text-neutral-400 mt-1">
              {trustPct >= 90 ? 'Top 10% of FOID users' : trustPct >= 70 ? 'Above average' : 'Complete more steps to improve'}
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom row ── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-5 items-start">

        {/* Verification progress */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-7">
          <div className="text-[16px] font-bold text-neutral-900 mb-1">Verification progress</div>
          <div className="text-[12.5px] text-neutral-400 mb-8">
            {allDone
              ? 'All steps complete — your identity credential is fully active'
              : 'Complete the remaining steps to maximise your trust score'
            }
          </div>

          {/* Steps with connectors */}
          <div className="flex items-start overflow-x-auto pb-2">
            {steps.map((step, i) => {
              const isLast   = i === steps.length - 1
              const nextDone = !isLast && steps[i + 1].done
              return (
                <div key={step.id} className="flex items-start flex-1 min-w-[72px]">
                  <div className="flex flex-col items-center gap-2.5 shrink-0 w-[72px]">
                    <div className={[
                      'w-11 h-11 rounded-full flex items-center justify-center',
                      step.done ? 'bg-brand-500' : 'bg-neutral-200',
                    ].join(' ')}>
                      <RemixIcon
                        name={step.icon}
                        size={20}
                        color={step.done ? '#fff' : '#a1a1aa'}
                      />
                    </div>
                    <span className={[
                      'text-[12px] font-medium text-center leading-tight',
                      step.done ? 'text-brand-600' : 'text-neutral-400',
                    ].join(' ')}>
                      {step.label}
                    </span>
                  </div>
                  {!isLast && (
                    <div className={[
                      'flex-1 h-[3px] mt-[22px] rounded-full hidden sm:block',
                      nextDone ? 'bg-brand-500' : 'bg-neutral-200',
                    ].join(' ')} />
                  )}
                </div>
              )
            })}
          </div>

          {/* ── Action cards ── */}
          <div className="flex flex-col gap-3 mt-8">

            {/* Verify BVN */}
            <div className={[
              'rounded-xl border p-4',
              bvnDone ? 'border-brand-200 bg-brand-50' : 'border-neutral-200 bg-white',
            ].join(' ')}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={[
                    'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                    bvnDone ? 'bg-brand-500' : 'bg-neutral-100',
                  ].join(' ')}>
                    <RemixIcon name={bvnDone ? 'ri-check-line' : 'ri-bank-line'} size={16} color={bvnDone ? '#fff' : '#a1a1aa'} />
                  </div>
                  <div>
                    <div className="text-[13.5px] font-semibold text-neutral-900">Verify BVN</div>
                    <div className="text-[12px] text-neutral-400">
                      {bvnDone ? 'Bank Verification Number confirmed' : 'Enter your 11-digit BVN to verify'}
                    </div>
                  </div>
                </div>
                {bvnDone ? (
                  <span className="text-[12px] font-semibold text-brand-600 shrink-0">Verified</span>
                ) : (
                  <button
                    onClick={() => setActiveStep(activeStep === 'bvn' ? null : 'bvn')}
                    className="shrink-0 px-3 py-1.5 rounded-lg bg-brand-500 text-white text-[12.5px] font-semibold hover:bg-brand-600 transition-colors"
                  >
                    {activeStep === 'bvn' ? 'Cancel' : 'Verify now'}
                  </button>
                )}
              </div>
              {activeStep === 'bvn' && !bvnDone && (
                <StepAction
                  type="bvn"
                  onSuccess={async () => { await refreshUser(); setActiveStep(null) }}
                />
              )}
            </div>

            {/* Liveness check */}
            <div className={[
              'rounded-xl border p-4',
              livenessVerified ? 'border-brand-200 bg-brand-50' : 'border-neutral-200 bg-white',
            ].join(' ')}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={[
                    'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                    livenessVerified ? 'bg-brand-500' : 'bg-neutral-100',
                  ].join(' ')}>
                    <RemixIcon name={livenessVerified ? 'ri-check-line' : 'ri-camera-line'} size={16} color={livenessVerified ? '#fff' : '#a1a1aa'} />
                  </div>
                  <div>
                    <div className="text-[13.5px] font-semibold text-neutral-900">Liveness check</div>
                    <div className="text-[12px] text-neutral-400">
                      {livenessVerified ? 'Face verified successfully' : 'Quick camera check to confirm your identity'}
                    </div>
                  </div>
                </div>
                {livenessVerified ? (
                  <span className="text-[12px] font-semibold text-brand-600 shrink-0">Verified</span>
                ) : (
                  <button
                    onClick={() => setActiveStep(activeStep === 'liveness' ? null : 'liveness')}
                    className="shrink-0 px-3 py-1.5 rounded-lg bg-brand-500 text-white text-[12.5px] font-semibold hover:bg-brand-600 transition-colors"
                  >
                    {activeStep === 'liveness' ? 'Cancel' : 'Start check'}
                  </button>
                )}
              </div>
              {activeStep === 'liveness' && !livenessVerified && (
                <StepAction
                  type="liveness"
                  onSuccess={() => { setLiveness(true); setActiveStep(null) }}
                />
              )}
            </div>

            {/* Verify phone */}
            <div className={[
              'rounded-xl border p-4',
              phoneVerified ? 'border-brand-200 bg-brand-50' : 'border-neutral-200 bg-white',
            ].join(' ')}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={[
                    'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                    phoneVerified ? 'bg-brand-500' : 'bg-neutral-100',
                  ].join(' ')}>
                    <RemixIcon name={phoneVerified ? 'ri-check-line' : 'ri-smartphone-line'} size={16} color={phoneVerified ? '#fff' : '#a1a1aa'} />
                  </div>
                  <div>
                    <div className="text-[13.5px] font-semibold text-neutral-900">Verify phone number</div>
                    <div className="text-[12px] text-neutral-400">
                      {phoneVerified ? `Number on file: ${user?.phone}` : 'Add your phone number to your profile'}
                    </div>
                  </div>
                </div>
                {phoneVerified ? (
                  <span className="text-[12px] font-semibold text-brand-600 shrink-0">Added</span>
                ) : (
                  <button
                    onClick={() => setActiveStep(activeStep === 'phone' ? null : 'phone')}
                    className="shrink-0 px-3 py-1.5 rounded-lg bg-brand-500 text-white text-[12.5px] font-semibold hover:bg-brand-600 transition-colors"
                  >
                    {activeStep === 'phone' ? 'Cancel' : 'Add number'}
                  </button>
                )}
              </div>
              {activeStep === 'phone' && !phoneVerified && (
                <StepAction
                  type="phone"
                  onSuccess={async () => { await refreshUser(); setActiveStep(null) }}
                />
              )}
            </div>

          </div>
        </div>

        {/* Linked accounts */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="text-[16px] font-bold text-neutral-900">Linked accounts &amp; credentials</div>
            {banks.length > 0 && (
              <span className="text-[12px] text-neutral-400">{banks.length} connected</span>
            )}
          </div>

          {banks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 gap-2 text-neutral-300">
              <RemixIcon name="ri-bank-line" size={36} color="#d4d4d8" />
              <span className="text-[13px] text-neutral-400">No banks connected yet</span>
              <button
                onClick={() => navigate('/dashboard/banks')}
                className="mt-1 text-[13px] font-semibold text-brand-600 hover:underline"
              >
                Connect a bank
              </button>
            </div>
          ) : (
            <div className="flex flex-col">
              {displayBanks.map((bank, i) => (
                <div
                  key={bank.id}
                  className={[
                    'flex items-center gap-3 py-4',
                    i < displayBanks.length - 1 || extraBanks > 0 ? 'border-b border-neutral-100' : '',
                  ].join(' ')}
                >
                  {bank.logo_url ? (
                    <img
                      src={bank.logo_url}
                      alt={bank.name}
                      className="w-9 h-9 rounded-lg object-cover shrink-0 border border-neutral-100"
                    />
                  ) : (
                    <div className="w-9 h-9 rounded-lg bg-brand-500 flex items-center justify-center shrink-0 text-white text-[14px] font-bold">
                      {bank.name.charAt(0)}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] font-semibold text-neutral-900 truncate">{bank.name}</div>
                    <div className="text-[12px] text-neutral-400">{formatLinkedDate(bank.created_at)}</div>
                  </div>
                  <span className="px-3 py-1 rounded-full bg-brand-100 text-brand-600 text-[12px] font-bold shrink-0">
                    {bank.status === 'verified' ? 'Linked' : bank.status}
                  </span>
                </div>
              ))}

              {extraBanks > 0 && (
                <button
                  onClick={() => navigate('/dashboard/banks')}
                  className="flex items-center justify-between py-3.5 text-[13.5px] font-semibold text-brand-600 hover:text-brand-700 transition-colors"
                >
                  <span>+{extraBanks} more bank{extraBanks > 1 ? 's' : ''}</span>
                  <RemixIcon name="ri-arrow-right-line" size={16} color="#C800DE" />
                </button>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
