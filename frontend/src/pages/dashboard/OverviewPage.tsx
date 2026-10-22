import {
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useNavigate } from 'react-router-dom'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'
import IncomeExpenseChart from '@/components/IncomeExpenseChart'
import { useCredential } from '@/contexts/CredentialContext'
import { useAuth } from '@/contexts/AuthContext'
import { useMonoData } from '@/hooks/useMonoData'
import type { CredentialState } from '@/types/foid'

/* ── Brand colours ──────────────────────────────────────────────────── */
const BRAND_LITE = '#f5d0fe'   // brand-200
const BRAND_DEEP = '#a21caf'   // brand-600

const CRED_MAX = 80
const credentialUsageData = [
  { platform: 'Wema',    pulls: 80 },
  { platform: 'Carbon',  pulls: 35 },
  { platform: 'Opay',    pulls: 68 },
  { platform: 'Kuda',    pulls: 18 },
  { platform: 'GT Bank', pulls: 22 },
].map(d => ({ ...d, remainder: CRED_MAX - d.pulls }))

/* ── Helpers ────────────────────────────────────────────────────────── */
const naira = (n: number) => '₦' + n.toLocaleString('en-NG')

/* ── State badge colours ────────────────────────────────────────────── */
const STATE_META: Record<CredentialState, { label: string; color: string; bg: string }> = {
  active:       { label: 'Active',       color: '#15803d', bg: '#dcfce7' },
  under_review: { label: 'Under Review', color: '#a16207', bg: '#fef9c3' },
  downgraded:   { label: 'Downgraded',   color: '#c2410c', bg: '#fff7ed' },
  revoked:      { label: 'Revoked',      color: '#dc2626', bg: '#fee2e2' },
}

/* ── Spending donut (driven by real category data) ───────────────────── */
const DONUT_PALETTE = ['#c026d3', '#f5941c', '#1e9e4a', '#2563eb', '#f59e0b', '#64748b']

interface DonutSeg { color: string; pct: number; label: string }

function SpendingDonut({ segs }: { segs: DonutSeg[] }) {
  const SIZE = 200, cx = SIZE / 2, cy = SIZE / 2, r = 72, SW = 16, GAP = 12
  const circ = 2 * Math.PI * r
  let cursor = -160

  const built = segs.map((s, i) => {
    const spanDeg = (s.pct / 100) * 360 - GAP
    const midDeg  = cursor + GAP / 2 + spanDeg / 2
    const entry   = { ...s, startDeg: cursor + GAP / 2, spanDeg, midDeg, color: DONUT_PALETTE[i % DONUT_PALETTE.length] }
    cursor += (s.pct / 100) * 360
    return entry
  })

  const toArc = (deg: number) => {
    const frac = deg / 360
    return `${frac * circ} ${circ - frac * circ}`
  }

  const badgePos = (midDeg: number) => {
    const rad = (midDeg * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }

  return (
    <div className="relative mx-auto" style={{ width: SIZE, height: SIZE }}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#ececec" strokeWidth={SW} />
        {built.map((s, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none"
            stroke={s.color} strokeWidth={SW} strokeLinecap="round"
            strokeDasharray={toArc(s.spanDeg)}
            transform={`rotate(${s.startDeg} ${cx} ${cy})`}
          />
        ))}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center"
        style={{ fontSize: 48, fontWeight: 800, color: '#c9c9c9', fontFamily: 'Georgia, serif', lineHeight: 1 }}>
        ₦
      </div>
      {built.map((s, i) => {
        const pos = badgePos(s.midDeg)
        return (
          <div key={i} className="absolute flex items-center justify-center rounded-full text-white font-bold"
            style={{ width: 28, height: 28, background: s.color, fontSize: 11,
              left: pos.x, top: pos.y, transform: 'translate(-50%, -50%)',
              boxShadow: '0 2px 5px rgba(0,0,0,0.18)' }}>
            {s.pct}
          </div>
        )
      })}
    </div>
  )
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function OverviewPage() {
  const { credential } = useCredential()
  const { user } = useAuth()
  const navigate = useNavigate()
  const stateMeta = STATE_META[credential.state]

  const isVerified = user?.email_verified ?? false
  const { banks, mtd, chartData, spendByCategory, loading } = useMonoData(isVerified)

  // Build donut segments from real spend-by-category
  const totalSpend = spendByCategory.reduce((s, c) => s + c.value, 0)
  const donutSegs: DonutSeg[] = totalSpend > 0
    ? spendByCategory.slice(0, 3).map(c => ({
        label: c.label,
        pct:   Math.round((c.value / totalSpend) * 100),
        color: '#c026d3',
      }))
    : [
        { label: 'Payroll',   pct: 46, color: '#c026d3' },
        { label: 'Logistics', pct: 31, color: '#1e9e4a'  },
        { label: 'Other',     pct: 23, color: '#f5941c'  },
      ]

  // Fallback display categories when no real data yet
  const displayCategories = totalSpend > 0
    ? spendByCategory.slice(0, 3).map((c, i) => ({
        label: c.label,
        pct: Math.round((c.value / totalSpend) * 100),
        color: DONUT_PALETTE[i % DONUT_PALETTE.length],
      }))
    : [
        { label: 'Payroll',   pct: 46, color: '#c026d3' },
        { label: 'Logistics', pct: 31, color: '#1e9e4a'  },
        { label: 'Other',     pct: 23, color: '#f5941c'  },
      ]

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">
            Welcome back, {user?.firstName ?? 'there'}
          </h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            Here's a snapshot of your identity, credentials, and business finances
          </p>
        </div>
        <button
          onClick={() => navigate('/dashboard/banks')}
          className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-white rounded-full font-semibold text-[14px] transition-colors shrink-0 w-full md:w-auto justify-center"
        >
          + Connect a Bank
        </button>
      </div>

      {/* ── Row 1 stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Connected Banks"
          value={loading ? '…' : String(banks.length)}
          sub={banks.length > 0
            ? banks.slice(0, 2).map(b => b.name).join(', ') + (banks.length > 2 ? ` +${banks.length - 2}` : '')
            : 'No banks connected yet'}
          subColor="text-brand-500 font-semibold"
          icon="ri-bank-line"
        />
        <StatCard label="Identity Verification" value="Verified"
          sub="Tier 2 · Full KYC complete" subColor="text-neutral-400" icon="ri-shield-user-line" />
        <StatCard label="Active Credentials" value="156"
          sub="Shared across 6 platforms" subColor="text-green-600 font-semibold" icon="ri-book-read-fill" />
        <StatCard label="AI Credit Balance" value="8420"
          sub="Covers ~52 more days" subColor="text-neutral-400" icon="ri-quill-pen-fill" />
      </div>

      {/* ── Row 2 — financial stat cards (live Mono data) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Monthly Income"
          value={loading ? '…' : (mtd.income > 0 ? naira(mtd.income) : '—')}
          sub={mtd.income > 0 ? 'This month · from connected banks' : 'Connect a bank to see income'}
          subColor="text-neutral-400"
          icon="₦"
        />
        <StatCard
          label="Monthly Expense"
          value={loading ? '…' : (mtd.expense > 0 ? naira(mtd.expense) : '—')}
          sub={mtd.expense > 0 ? `${mtd.income > 0 ? Math.round((mtd.expense / mtd.income) * 100) : 0}% of income` : 'No expense data yet'}
          subColor="text-neutral-400"
          icon="ri-hand-coin-line"
        />
        <StatCard
          label="Estimated Tax (7.5%)"
          value={loading ? '…' : (mtd.tax > 0 ? naira(mtd.tax) : '—')}
          sub="On net profit this month"
          subColor="text-neutral-400"
          icon="ri-percent-line"
        />
        <StatCard label="Verification Requests" value="3"
          sub="This week · 1 needs your action" subColor="text-neutral-400" icon="ri-profile-fill" />
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_450px] gap-7 py-4">

        {/* Income vs Expenses — live chart data */}
        <IncomeExpenseChart
          data={chartData.length > 0 ? chartData : undefined}
          subtitle={
            chartData.length > 0
              ? `Last ${chartData.length} days across all connected banks`
              : 'Sample data — connect a bank to see real activity'
          }
        />

        {/* Credential card */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5 flex flex-col">
          <div className="font-bold text-[15px] text-neutral-900 mb-4">Your verification credential</div>
          <div className="h-px bg-neutral-100 -mx-5 mb-5" />
          <div className="flex flex-col flex-1 justify-between gap-3">
            <div className="relative rounded-2xl overflow-hidden p-5 min-h-[180px] flex flex-col justify-between"
              style={{ background: '#7B61FF' }}>
              <div className="absolute inset-0 pointer-events-none"
                style={{ backgroundImage: 'url(/noise.png)', backgroundSize: '160px', opacity: 0.08 }} />
              <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden="true" style={{ opacity: 0.12 }}>
                <defs>
                  <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
                    <path d="M 24 0 L 0 0 0 24" fill="none" stroke="white" strokeWidth="0.5" />
                  </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#grid)" />
              </svg>
              <img src="/shape.png" alt="" aria-hidden="true"
                className="absolute right-0 top-0 h-full pointer-events-none select-none"
                style={{ width: '55%', objectFit: 'cover', objectPosition: 'left center', opacity: 0.95 }} />
              <div className="absolute top-4 right-4 z-10">
                <span className="text-[11px] font-bold px-3 py-1 rounded-full"
                  style={{ background: stateMeta.bg, color: stateMeta.color }}>
                  {stateMeta.label}
                </span>
              </div>
              <div className="relative z-10">
                <div className="text-[11px] font-bold tracking-[2px] text-white/70 uppercase mb-3">FOID</div>
                <div>
                  <div className="text-[10px] font-bold tracking-widest text-white/60 uppercase mb-0.5">Credential State</div>
                  <div className="text-[18px] font-extrabold text-white leading-none"
                    style={{ fontFamily: "'Neue Machina', sans-serif" }}>
                    {stateMeta.label}
                  </div>
                </div>
              </div>
              <div className="relative z-10 mt-4">
                <div className="text-[10px] font-bold tracking-widest text-white/60 uppercase mb-0.5">Holder</div>
                <div className="text-[15px] font-semibold text-white">
                  {user?.firstName ?? ''} {user?.lastName?.[0] ?? ''}.
                </div>
              </div>
            </div>
            <button className="w-full mt-3 py-2.5 border border-neutral-200 rounded-xl text-[13.5px] font-semibold text-neutral-800 flex items-center justify-center gap-2 hover:bg-neutral-50 transition-colors">
              <RemixIcon name="ri-qr-code-line font-normal" size={18} color="#18181b" />
              View my FOID code
            </button>
          </div>
        </div>

        {/* Credential usage bar chart */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="font-bold text-[15px] text-neutral-900 mb-0.5">Where your credential is used</div>
          <div className="text-[12px] text-neutral-400 mb-4">Verification pulls by connected platforms</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={credentialUsageData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }} barSize={44} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
              <XAxis dataKey="platform" tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} domain={[0, CRED_MAX]} />
              <Tooltip
                formatter={(val, name) => name === 'remainder' ? null : [val, 'Pulls']}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e4e4e7' }}
              />
              <Bar dataKey="pulls" stackId="a" fill={BRAND_DEEP} radius={[0, 0, 4, 4]} />
              <Bar dataKey="remainder" stackId="a" fill={BRAND_LITE} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Spending breakdown — live Mono categories */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="font-bold text-[15px] text-neutral-900 mb-0.5">Spending breakdown</div>
          <div className="text-[12px] text-neutral-400 mb-4">
            {totalSpend > 0 ? 'This month, by category (Mono)' : 'Sample data — connect a bank to see real spend'}
          </div>
          <div className="h-px bg-neutral-100 -mx-5 mb-5" />

          <SpendingDonut segs={donutSegs} />

          <div className="flex flex-col gap-[18px] mt-6">
            {(() => {
              const max = Math.max(...displayCategories.map(c => c.pct))
              return displayCategories.map(c => (
                <div key={c.label} className="grid items-center gap-3"
                  style={{ gridTemplateColumns: 'minmax(84px, auto) 1fr' }}>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: c.color }} />
                    <span className="text-[13.5px] font-semibold text-neutral-900">{c.label}</span>
                  </div>
                  <div className="h-2 rounded-full bg-neutral-100 overflow-hidden">
                    <div className="h-full rounded-full"
                      style={{ width: `${(c.pct / max) * 100}%`, background: c.color }} />
                  </div>
                </div>
              ))
            })()}
          </div>
        </div>

      </div>
    </div>
  )
}
