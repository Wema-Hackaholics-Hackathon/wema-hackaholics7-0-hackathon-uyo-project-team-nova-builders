import RemixIcon from '@/components/RemixIcon'

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
            <stop offset="100%" stopColor="#c026d3" />
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

/* ── Verification steps ─────────────────────────────────────────────── */
const VERIF_STEPS = [
  { label: 'Phone',    icon: 'ri-smartphone-line', done: true  },
  { label: 'Email',    icon: 'ri-mail-line',        done: true  },
  { label: 'BVN',      icon: 'ri-bank-line',        done: true  },
  { label: 'NIN',      icon: 'ri-shield-user-line', done: false },
  { label: 'Liveness', icon: 'ri-camera-line',      done: false },
]

/* ── Linked accounts ────────────────────────────────────────────────── */
const LINKED_ACCOUNTS = [
  { name: 'Wema Bank', date: 'Linked 12 Jun 2026', logo: '/wema.jpg' },
  { name: 'GT Bank',   date: 'Linked 12 Jun 2026', logo: '/GTCO.jpg' },
]

/* ── Page ───────────────────────────────────────────────────────────── */
export default function MyIdentityPage() {
  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[26px] font-bold tracking-tight text-neutral-900">My Identity</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">Your verified digital identity, generated once and reusable everywhere</p>
        </div>
        <button className="flex items-center gap-2 px-5 py-2.5 border border-neutral-200 rounded-full font-semibold text-[14px] text-neutral-800 bg-white hover:bg-neutral-50 transition-colors shrink-0">
          <RemixIcon name="ri-download-2-line" size={20} /> Download Identity Summary
        </button>
      </div>

      {/* ── Hero card ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl pl-9 pr-[54px] py-10 flex items-center gap-7">
        {/* Avatar */}
        <img
          src="/avatar.png"
          alt="Daniel Afolabi"
          className="w-[86px] h-[86px] rounded-full object-cover border-[3.5px] border-brand-400 shrink-0"
        />

        {/* Name + badge */}
        <div>
          <div className="text-[22px] font-bold text-neutral-900 mb-2">Daniel Afolabi</div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-100 text-brand-600 text-[13px] font-semibold">
            Tier 2 · Fully verified
          </span>
        </div>

        {/* Trust ring — pushed right */}
        <div className="ml-auto flex items-center gap-5">
          <TrustRing pct={98} />
          <div>
            <div className="text-[11px] text-neutral-400 mb-1">Trust Score</div>
            <div className="text-[22px] font-extrabold text-neutral-900 leading-none">98.4/100</div>
            <div className="text-[12px] text-neutral-400 mt-1">Top 8% of verified FOID users</div>
          </div>
        </div>
      </div>

      {/* ── Bottom row ── */}
      <div className="grid grid-cols-[1fr_360px] gap-5">

        {/* Verification progress */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-7">
          <div className="text-[16px] font-bold text-neutral-900 mb-1">Verification progress</div>
          <div className="text-[12.5px] text-neutral-400 mb-10">All steps complete — your identity credential is fully active</div>

          {/* Steps with connectors */}
          <div className="flex items-start justify-center">
            {VERIF_STEPS.map((step, i) => {
              const isLast = i === VERIF_STEPS.length - 1
              const nextDone = !isLast && VERIF_STEPS[i + 1].done
              return (
                <div key={step.label} className="flex items-start flex-1">
                  <div className="flex flex-col items-center gap-2.5 flex-shrink-0">
                    {/* Icon circle */}
                    <div className={[
                      'w-11 h-11 rounded-full flex items-center justify-center shrink-0',
                      step.done ? 'bg-brand-500' : 'bg-neutral-200',
                    ].join(' ')}>
                      <RemixIcon name={step.icon} size={20} color={step.done ? '#fff' : '#a1a1aa'} />
                    </div>
                    <span className="text-[12px] text-neutral-500 font-medium text-center">{step.label}</span>
                  </div>
                  {/* Connector line */}
                  {!isLast && (
                    <div className={[
                      'flex-1 h-[3px] mt-[22px] mx-1 rounded-full',
                      nextDone ? 'bg-brand-500' : 'bg-neutral-200',
                    ].join(' ')} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Linked accounts */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-6">
          <div className="text-[16px] font-bold text-neutral-900 mb-4">Linked accounts &amp; credentials</div>
          <div className="flex flex-col">
            {LINKED_ACCOUNTS.map((acct, i) => (
              <div
                key={acct.name}
                className={[
                  'flex items-center gap-3 py-4',
                  i < LINKED_ACCOUNTS.length - 1 ? 'border-b border-neutral-100' : '',
                ].join(' ')}
              >
                {/* Bank logo */}
                <img src={acct.logo} alt={acct.name} className="w-9 h-9 rounded-lg object-cover shrink-0 border border-neutral-100" />
                <div className="flex-1 min-w-0">
                  <div className="text-[14px] font-semibold text-neutral-900">{acct.name}</div>
                  <div className="text-[12px] text-neutral-400">{acct.date}</div>
                </div>
                <span className="px-3 py-1 rounded-full bg-brand-100 text-brand-600 text-[12px] font-bold shrink-0">
                  Linked
                </span>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
