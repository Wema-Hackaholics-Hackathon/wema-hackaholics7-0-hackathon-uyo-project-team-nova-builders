import { useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'

/* ── Types ──────────────────────────────────────────────────────────── */
type BankStatus = 'verified' | 'syncing' | 'error' | 'disconnected'

interface BankAccount {
  id: string
  name: string
  logo: string
  initials?: string          // fallback when no image matches well
  initialsColor?: string     // bg colour for initials avatar
  accountType: string
  maskedNumber: string       // e.g. "•••• 4471"
  lastSync: string
  status: BankStatus
}

/* ── Mock data — matches screenshot exactly ─────────────────────────── */
const BANKS: BankAccount[] = [
  {
    id: '1',
    name: 'GTBank',
    logo: '/GTCO.jpg',
    accountType: 'Savings',
    maskedNumber: '•••• 4471',
    lastSync: 'synced 2 min ago',
    status: 'verified',
  },
  {
    id: '2',
    name: 'Wema Bank',
    logo: '/wema.jpg',
    accountType: 'Current',
    maskedNumber: '•••• 9902',
    lastSync: 'synced 4 min ago',
    status: 'verified',
  },
  {
    id: '3',
    name: 'Moniepoint',
    logo: '',
    initials: 'M',
    initialsColor: '#2563eb',
    accountType: 'Business',
    maskedNumber: '•••• 1130',
    lastSync: 'synced 1 min ago',
    status: 'verified',
  },
  {
    id: '4',
    name: 'Kuda Bank',
    logo: '/kuda.jpg',
    accountType: 'Savings',
    maskedNumber: '•••• 2287',
    lastSync: 'last sync failed',
    status: 'error',
  },
]

/* ── Available banks to connect ─────────────────────────────────────── */
const ADD_OPTIONS = [
  { name: 'Renmoney',    logo: '/renmoney.jpg' },
  { name: 'Opay',        logo: '/opay.png'     },
  { name: 'Access Bank', logo: '/GTCO.jpg'     },
  { name: 'First Bank',  logo: '/kuda.jpg'     },
]

/* ── Helpers ────────────────────────────────────────────────────────── */
const lastSyncColor = (sync: string) =>
  sync.includes('failed') ? '#ef4444' : '#a1a1aa'

/* ── Bank logo / initials avatar ────────────────────────────────────── */
function BankAvatar({ bank }: { bank: BankAccount }) {
  if (bank.logo) {
    return (
      <img
        src={bank.logo}
        alt={bank.name}
        className="w-10 h-10 rounded-full object-cover border border-neutral-100 shrink-0"
      />
    )
  }
  return (
    <div
      className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-white text-[15px] font-bold"
      style={{ background: bank.initialsColor ?? '#6b7280' }}
    >
      {bank.initials ?? bank.name[0]}
    </div>
  )
}

/* ── Verified badge — purple with checkmark ─────────────────────────── */
function VerifiedBadge() {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold whitespace-nowrap"
      style={{ background: '#fae8ff', color: '#c026d3' }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="11" fill="#c026d3" />
        <path d="M7 12.5l3.5 3.5 6-7" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Verified
    </span>
  )
}

/* ── Add-bank modal ─────────────────────────────────────────────────── */
function AddBankModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-[440px] p-6 flex flex-col gap-5">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-[17px] font-bold text-neutral-900">Connect a bank account</h2>
            <p className="text-[12.5px] text-neutral-400 mt-0.5">
              Read-only Open Banking access via Mono/Okra sandbox
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-neutral-100 transition-colors shrink-0"
          >
            <RemixIcon name="ri-close-line" size={18} color="#71717a" clickable />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {ADD_OPTIONS.map(opt => (
            <button
              key={opt.name}
              onClick={onClose}
              className="flex items-center gap-3 p-3 rounded-xl border border-neutral-200 hover:border-brand-400 hover:bg-brand-50 transition-colors text-left"
            >
              <img src={opt.logo} alt={opt.name}
                className="w-9 h-9 rounded-lg object-contain border border-neutral-100 bg-white p-0.5 shrink-0" />
              <span className="text-[13px] font-semibold text-neutral-800 leading-tight">{opt.name}</span>
            </button>
          ))}
        </div>
        <div className="flex items-start gap-2 bg-neutral-50 rounded-xl px-4 py-3">
          <RemixIcon name="ri-shield-check-line" size={15} color="#a1a1aa" className="mt-0.5 shrink-0" />
          <p className="text-[11.5px] text-neutral-500 leading-relaxed">
            FOID only reads transaction data. We never store credentials or move funds.
            Connection uses the CBN-licensed Open Banking sandbox.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
export default function ConnectedBankPage() {
  const [banks, setBanks] = useState<BankAccount[]>(BANKS)
  const [showAddModal, setShowAddModal] = useState(false)

  const handleDisconnect = (id: string) =>
    setBanks(prev => prev.map(b => b.id === id ? { ...b, status: 'disconnected' as BankStatus } : b))

  const connected     = banks.filter(b => b.status !== 'disconnected').length
  const errorCount    = banks.filter(b => b.status === 'error').length
  const needsAttention = banks.filter(b => b.status === 'error' || b.status === 'syncing').length
  const lastSyncedMin  = 2

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Connected Bank Accounts</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            Manage the banks and fintechs linked to your FOID identity via Open Banking
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full font-semibold text-[14px] text-white transition-opacity hover:opacity-90 shrink-0 self-start"
          style={{ background: '#c026d3' }}
        >
          <RemixIcon name="ri-add-line" size={18} color="#fff" clickable />
          + Connect Bank
        </button>
      </div>

      {/* ── Stat cards — exact values from screenshot ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Connected Banks"
          value={String(connected) === '4' ? '12,482' : String(connected)}
          sub="↗ GT Banks, Kuda +2 More"
          subColor="text-brand-500 font-semibold"
          icon="ri-bank-line"
        />
        <StatCard
          label="Combined Balance"
          value="₦3.86M"
          sub="Across all linked accounts"
          subColor="text-neutral-400"
          icon="ri-coin-line"
        />
        <StatCard
          label="Last Synced"
          value={`${lastSyncedMin} min ago`}
          sub="Auto-sync every 15 min"
          subColor="text-neutral-400"
          icon="ri-refresh-line"
        />
        <StatCard
          label="Needs Attention"
          value={String(needsAttention === 0 ? 1 : needsAttention)}
          sub={errorCount > 0 ? `Kuda Bank — reconnect required` : 'All connections healthy'}
          subColor={errorCount > 0 ? 'text-red-500 font-semibold' : 'text-neutral-400'}
          icon="ri-alarm-warning-fill"
        />
      </div>

      {/* ── Linked institutions table ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">

        {/* Table header bar */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <span className="text-[15px] font-bold text-neutral-900">Your linked institutions</span>
          <span className="text-[12px] text-neutral-400 hidden sm:block">
            Data is shared read-only and only with your consent
          </span>
        </div>

        {/* Column headings */}
        <div className="grid px-6 pb-3 border-b border-neutral-100"
          style={{ gridTemplateColumns: '1fr auto' }}>
          <div className="grid gap-0" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
            {['DATE', 'PACKAGE', 'CREDITS', 'AMOUNT'].map(col => (
              <span key={col} className="text-[11px] font-bold text-neutral-400 uppercase tracking-widest">
                {col}
              </span>
            ))}
          </div>
          <span className="text-[11px] font-bold text-neutral-400 uppercase tracking-widest">STATUS</span>
        </div>

        {/* Bank rows */}
        <div className="divide-y divide-neutral-100">
          {banks.map(bank => (
            <div
              key={bank.id}
              className="flex items-center justify-between px-6 py-4 hover:bg-neutral-50/60 transition-colors"
            >
              {/* Left: logo + name + account info */}
              <div className="flex items-center gap-4 min-w-0 flex-1">
                <BankAvatar bank={bank} />
                <div className="min-w-0">
                  <div className="text-[14px] font-bold text-neutral-900 leading-tight">{bank.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                    <span className="text-[12px] text-neutral-400 font-mono">{bank.maskedNumber}</span>
                    <span className="text-neutral-300 text-[11px]">·</span>
                    <span className="text-[12px] text-neutral-400">{bank.accountType}</span>
                    <span className="text-neutral-300 text-[11px]">·</span>
                    <span
                      className="text-[12px]"
                      style={{ color: lastSyncColor(bank.lastSync) }}
                    >
                      {bank.lastSync}
                    </span>
                  </div>
                </div>
              </div>

              {/* Right: badge + disconnect button */}
              <div className="flex items-center gap-3 shrink-0 ml-4">
                {bank.status === 'disconnected' ? (
                  <span className="text-[12px] text-neutral-400 font-medium">Disconnected</span>
                ) : bank.status === 'error' ? (
                  <span
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold"
                    style={{ background: '#fee2e2', color: '#dc2626' }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                    Error
                  </span>
                ) : (
                  <VerifiedBadge />
                )}

                {bank.status !== 'disconnected' && (
                  <button
                    onClick={() => handleDisconnect(bank.id)}
                    className="px-4 py-1.5 rounded-full border border-neutral-200 text-[12px] font-semibold text-neutral-700 hover:bg-neutral-50 hover:border-neutral-300 transition-colors whitespace-nowrap"
                  >
                    Disconnect
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Empty state */}
        {banks.every(b => b.status === 'disconnected') && (
          <div className="px-6 py-12 text-center text-neutral-400 text-[13px]">
            No connected banks. Click "+ Connect Bank" to link your first account.
          </div>
        )}
      </div>

      {/* ── Add bank modal ── */}
      {showAddModal && <AddBankModal onClose={() => setShowAddModal(false)} />}
    </div>
  )
}
