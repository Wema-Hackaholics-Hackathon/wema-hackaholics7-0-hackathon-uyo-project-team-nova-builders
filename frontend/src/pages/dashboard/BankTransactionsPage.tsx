import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import RemixIcon from '@/components/RemixIcon'
import { api } from '@/lib/api'
import type { ConnectedBank, MonoTransaction } from '@/types/foid'

/* ── Helpers ─────────────────────────────────────────────────────── */
function koboToNaira(kobo: number): string {
  return `₦${(kobo / 100).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-NG', {
      day: '2-digit', month: 'short', year: 'numeric',
    })
  } catch {
    return iso.slice(0, 10)
  }
}

/* ── Type badge ───────────────────────────────────────────────────── */
function TypeBadge({ type }: { type: string }) {
  const isCredit = type === 'credit'
  return (
    <span
      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide"
      style={{
        background: isCredit ? '#dcfce7' : '#fee2e2',
        color: isCredit ? '#16a34a' : '#dc2626',
      }}
    >
      <span className="text-[13px]">{isCredit ? '↑' : '↓'}</span>
      {type}
    </span>
  )
}

/* ════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════ */
export default function BankTransactionsPage() {
  const { bankId } = useParams<{ bankId: string }>()
  const navigate = useNavigate()

  const [bank, setBank] = useState<ConnectedBank | null>(null)
  const [transactions, setTransactions] = useState<MonoTransaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filter state
  const [typeFilter, setTypeFilter] = useState<'all' | 'credit' | 'debit'>('all')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!bankId) return
    setLoading(true)
    setError('')
    try {
      // Fetch bank details + transactions in parallel
      const [banksRes, txRes] = await Promise.all([
        api.get<ConnectedBank[]>('/banks/connected'),
        api.get<MonoTransaction[]>(`/banks/${bankId}/transactions`, {
          params: { limit: 200 },
        }),
      ])
      const found = banksRes.data.find(b => b.id === bankId) ?? null
      setBank(found)
      setTransactions(txRes.data)
    } catch {
      setError('Could not load transactions. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [bankId])

  useEffect(() => { void load() }, [load])

  // Derived list
  const filtered = transactions.filter(tx => {
    if (typeFilter !== 'all' && tx.type !== typeFilter) return false
    if (search) {
      const q = search.toLowerCase()
      return tx.narration.toLowerCase().includes(q) || (tx.category ?? '').toLowerCase().includes(q)
    }
    return true
  })

  // Aggregates over *full* (unfiltered) list
  const totalCredits  = transactions.filter(t => t.type === 'credit').reduce((s, t) => s + t.amount, 0)
  const totalDebits   = transactions.filter(t => t.type === 'debit').reduce((s, t) => s + t.amount, 0)
  const latestBalance = transactions.length > 0 ? transactions[0].balance : null

  return (
    <div className="flex flex-col gap-5">

      {/* ── Back + header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="flex items-start gap-3">
          <button
            onClick={() => navigate('/dashboard/banks')}
            className="mt-1 p-1.5 rounded-full hover:bg-neutral-100 transition-colors shrink-0"
          >
            <RemixIcon name="ri-arrow-left-line" size={18} color="#71717a" clickable />
          </button>
          <div>
            <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">
              {bank ? bank.name : 'Bank'} Transactions
            </h1>
            <p className="text-neutral-500 mt-1 text-[13.5px]">
              {bank?.masked_number && <span className="font-mono mr-2">{bank.masked_number}</span>}
              Sandbox transaction data from Mono Open Banking
            </p>
          </div>
        </div>
        <button
          onClick={() => void load()}
          className="flex items-center gap-2 px-4 py-2 rounded-full border border-neutral-200 text-[13px] font-semibold text-neutral-700 hover:bg-neutral-50 transition-colors shrink-0 self-start"
        >
          <RemixIcon name="ri-refresh-line" size={15} color="#71717a" clickable />
          Refresh
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-[13px] text-red-700">
          <RemixIcon name="ri-error-warning-line" size={15} color="#dc2626" />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">
            <RemixIcon name="ri-close-line" size={14} clickable />
          </button>
        </div>
      )}

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: 'Total Credits', value: koboToNaira(totalCredits), sub: `${transactions.filter(t => t.type === 'credit').length} transactions`, color: '#16a34a' },
          { label: 'Total Debits',  value: koboToNaira(totalDebits),  sub: `${transactions.filter(t => t.type === 'debit').length} transactions`,  color: '#dc2626' },
          { label: 'Latest Balance', value: latestBalance !== null ? koboToNaira(latestBalance) : '—', sub: 'After most recent transaction', color: '#c026d3' },
        ].map(c => (
          <div key={c.label} className="bg-white border border-neutral-200 rounded-2xl p-5">
            <p className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wide">{c.label}</p>
            <p className="text-[22px] font-bold mt-1" style={{ color: c.color }}>{c.value}</p>
            <p className="text-[12px] text-neutral-400 mt-0.5">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <RemixIcon name="ri-search-line" size={15} color="#a1a1aa"
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            placeholder="Search narration or category…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-neutral-200 text-[13px] focus:outline-none focus:ring-2 focus:ring-purple-200"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'credit', 'debit'] as const).map(f => (
            <button
              key={f}
              onClick={() => setTypeFilter(f)}
              className="px-4 py-2 rounded-full text-[12px] font-semibold border transition-colors capitalize"
              style={typeFilter === f
                ? { background: '#c026d3', color: '#fff', borderColor: '#c026d3' }
                : { background: '#fff', color: '#71717a', borderColor: '#e5e7eb' }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* ── Transactions table ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">
        <div className="px-6 pt-5 pb-3 border-b border-neutral-100 flex items-center justify-between">
          <span className="text-[15px] font-bold text-neutral-900">
            {filtered.length} transaction{filtered.length !== 1 ? 's' : ''}
          </span>
          {search || typeFilter !== 'all' ? (
            <button onClick={() => { setSearch(''); setTypeFilter('all') }}
              className="text-[12px] text-neutral-400 hover:text-neutral-600">Clear filters</button>
          ) : null}
        </div>

        {loading && (
          <div className="px-6 py-12 text-center text-[13px] text-neutral-400">
            <RemixIcon name="ri-loader-4-line" size={22} color="#a1a1aa" className="mx-auto mb-2 animate-spin" />
            Loading transactions from Mono…
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="px-6 py-12 text-center text-[13px] text-neutral-400">
            No transactions found{search ? ' matching your search' : ''}.
          </div>
        )}

        {!loading && filtered.map(tx => (
          <div key={tx.id}
            className="flex items-center justify-between px-6 py-4 border-b border-neutral-100 last:border-b-0 hover:bg-neutral-50/60 transition-colors">
            {/* Left */}
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center shrink-0"
                style={{ background: tx.type === 'credit' ? '#dcfce7' : '#fee2e2' }}
              >
                <RemixIcon
                  name={tx.type === 'credit' ? 'ri-arrow-down-line' : 'ri-arrow-up-line'}
                  size={16}
                  color={tx.type === 'credit' ? '#16a34a' : '#dc2626'}
                />
              </div>
              <div className="min-w-0">
                <p className="text-[13.5px] font-semibold text-neutral-900 truncate">{tx.narration}</p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <span className="text-[11.5px] text-neutral-400">{fmtDate(tx.date)}</span>
                  {tx.category && tx.category !== 'unknown' && (
                    <>
                      <span className="text-neutral-300 text-[10px]">·</span>
                      <span className="text-[11.5px] text-neutral-400 capitalize">{tx.category}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            {/* Right */}
            <div className="flex flex-col items-end gap-1 ml-4 shrink-0">
              <span
                className="text-[14px] font-bold"
                style={{ color: tx.type === 'credit' ? '#16a34a' : '#dc2626' }}
              >
                {tx.type === 'credit' ? '+' : '−'}{koboToNaira(tx.amount)}
              </span>
              <TypeBadge type={tx.type} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
