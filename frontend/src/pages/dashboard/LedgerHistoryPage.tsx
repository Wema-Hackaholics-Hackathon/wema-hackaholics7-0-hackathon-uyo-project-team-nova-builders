import { useEffect, useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import type { LedgerEntry } from '@/types/foid'

/* ── Helpers ─────────────────────────────────────────────────────────── */
const naira = (n: number) => '₦' + Math.abs(n).toLocaleString('en-NG', { maximumFractionDigits: 0 })

/* ── Mock data shown to unverified users (preview mode) ─────────────── */
const MOCK_ALL_ENTRIES: LedgerEntry[] = [
  { id: 'm1',  entry_date: '2026-07-14', description: 'Uber fleet — weekly delivery run',          category: 'Logistics', entry_type: 'expense', amount: '48200',  source: 'receipt', confidence: 0.98, raw_file_path: null, created_at: '' },
  { id: 'm2',  entry_date: '2026-07-13', description: 'Client payment — Studio Kola invoice #114', category: 'Sales',     entry_type: 'income',  amount: '320000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm3',  entry_date: '2026-07-12', description: 'Notion + Figma team subscription',          category: 'Software',  entry_type: 'expense', amount: '31500',  source: 'receipt', confidence: 0.96, raw_file_path: null, created_at: '' },
  { id: 'm4',  entry_date: '2026-07-11', description: 'Instagram ad campaign — July push',          category: 'Marketing', entry_type: 'expense', amount: '60000',  source: 'invoice', confidence: 0.93, raw_file_path: null, created_at: '' },
  { id: 'm5',  entry_date: '2026-07-10', description: 'Payroll — 6 staff, first half July',         category: 'Payroll',   entry_type: 'expense', amount: '320000', source: 'receipt', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm6',  entry_date: '2026-07-08', description: 'Diesel generator refuel — office',           category: 'Utilities', entry_type: 'expense', amount: '22400',  source: 'invoice', confidence: 0.91, raw_file_path: null, created_at: '' },
  { id: 'm7',  entry_date: '2026-07-06', description: 'Client payment — Lagos Fabrics Ltd',         category: 'Sales',     entry_type: 'income',  amount: '540000', source: 'receipt', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm8',  entry_date: '2026-07-05', description: 'Shopify subscription — monthly',             category: 'Software',  entry_type: 'expense', amount: '18200',  source: 'receipt', confidence: 0.99, raw_file_path: null, created_at: '' },
  { id: 'm9',  entry_date: '2026-07-04', description: 'Client retainer — Vance Studios',            category: 'Sales',     entry_type: 'income',  amount: '180000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm10', entry_date: '2026-07-03', description: 'Office supplies & stationery',               category: 'Other',     entry_type: 'expense', amount: '74000',  source: 'receipt', confidence: 0.87, raw_file_path: null, created_at: '' },
  { id: 'm11', entry_date: '2026-07-02', description: 'Electricity bill — PHCN July',               category: 'Utilities', entry_type: 'expense', amount: '41500',  source: 'invoice', confidence: 0.94, raw_file_path: null, created_at: '' },
  { id: 'm12', entry_date: '2026-07-01', description: 'Client payment — Apex Holdings',             category: 'Sales',     entry_type: 'income',  amount: '210000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm13', entry_date: '2026-06-30', description: 'Facebook Ads — June retargeting',            category: 'Marketing', entry_type: 'expense', amount: '80700',  source: 'invoice', confidence: 0.95, raw_file_path: null, created_at: '' },
  { id: 'm14', entry_date: '2026-06-29', description: 'Uber fleet — weekly delivery run',           category: 'Logistics', entry_type: 'expense', amount: '48200',  source: 'receipt', confidence: 0.98, raw_file_path: null, created_at: '' },
  { id: 'm15', entry_date: '2026-06-28', description: 'Staff payroll — June second tranche',        category: 'Payroll',   entry_type: 'expense', amount: '640000', source: 'bank',    confidence: 0.99, raw_file_path: null, created_at: '' },
  { id: 'm16', entry_date: '2026-06-27', description: 'Client payment — Taye Digital',              category: 'Sales',     entry_type: 'income',  amount: '150000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm17', entry_date: '2026-06-26', description: 'Google Workspace subscription',              category: 'Software',  entry_type: 'expense', amount: '12500',  source: 'receipt', confidence: 0.97, raw_file_path: null, created_at: '' },
  { id: 'm18', entry_date: '2026-06-25', description: 'Cold storage diesel — Apapa',                category: 'Logistics', entry_type: 'expense', amount: '55000',  source: 'receipt', confidence: 0.92, raw_file_path: null, created_at: '' },
  { id: 'm19', entry_date: '2026-06-24', description: 'Client payment — Nova Properties',           category: 'Sales',     entry_type: 'income',  amount: '480000', source: 'bank',    confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm20', entry_date: '2026-06-23', description: 'Office printer cartridges',                  category: 'Other',     entry_type: 'expense', amount: '28000',  source: 'receipt', confidence: 0.88, raw_file_path: null, created_at: '' },
  { id: 'm21', entry_date: '2026-06-22', description: 'Instagram ad campaign — June push',          category: 'Marketing', entry_type: 'expense', amount: '65200',  source: 'invoice', confidence: 0.93, raw_file_path: null, created_at: '' },
]
const MOCK_HISTORY_STATS = { total_entries: 2614, auto_categorised_pct: 97.1, exports_this_month: 9 }

/* ── Category pill ───────────────────────────────────────────────────── */
const CAT_COLORS: Record<string, { border: string; color: string }> = {
  Logistics: { border: '#bfdbfe', color: '#2563eb' }, Sales:     { border: '#bbf7d0', color: '#16a34a' },
  Software:  { border: '#ddd6fe', color: '#7c3aed' }, Payroll:   { border: '#f5d0fe', color: '#c026d3' },
  Marketing: { border: '#fed7aa', color: '#c2410c' }, Utilities: { border: '#fde68a', color: '#92400e' },
  Other:     { border: '#d4d4d8', color: '#71717a' },
}
function CategoryPill({ label }: { label: string }) {
  const c = CAT_COLORS[label] ?? { border: '#d4d4d8', color: '#71717a' }
  return (
    <span className="inline-flex px-3 py-1 rounded-full text-[12px] font-semibold whitespace-nowrap"
      style={{ border: `1px solid ${c.border}`, color: c.color, background: 'transparent' }}>
      {label}
    </span>
  )
}

/* ── Source icon ─────────────────────────────────────────────────────── */
const SOURCE_ICON: Record<string, string> = {
  receipt: 'ri-receipt-line', invoice: 'ri-file-text-line', bank: 'ri-bank-line',
}

/* ── Filter tabs ─────────────────────────────────────────────────────── */
type Filter = 'All' | 'Income' | 'Expense'
const TABS: Filter[] = ['All', 'Income', 'Expense']

interface Stats {
  total_entries: number
  auto_categorised_pct: number
  exports_this_month: number
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
const PAGE_SIZE = 7

export default function LedgerHistory() {
  const { user } = useAuth()
  const isVerified = user?.email_verified ?? false

  const [allEntries, setAllEntries] = useState<LedgerEntry[]>([])
  const [stats, setStats]           = useState<Stats | null>(null)
  const [loadingData, setLoading]   = useState(true)
  const [filter, setFilter]         = useState<Filter>('All')
  const [search, setSearch]         = useState('')
  const [page, setPage]             = useState(1)
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [exporting, setExporting]   = useState<'csv' | 'pdf' | null>(null)

  useEffect(() => {
    if (!isVerified) { setLoading(false); return }
    setLoading(true)
    Promise.all([
      api.get<LedgerEntry[]>('/ledger', { params: { limit: 500 } }),
      api.get<Stats>('/ledger/stats'),
    ])
      .then(([eRes, sRes]) => { setAllEntries(eRes.data); setStats(sRes.data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [isVerified])

  // ── Use mock data for unverified users ───────────────────────────────
  const displayEntries = isVerified ? allEntries : MOCK_ALL_ENTRIES
  const displayStats   = isVerified ? stats      : MOCK_HISTORY_STATS

  /* Filter + search */
  const filtered = displayEntries.filter(e => {
    if (filter === 'Income'  && e.entry_type !== 'income')  return false
    if (filter === 'Expense' && e.entry_type !== 'expense') return false
    if (search) {
      const q = search.toLowerCase()
      return (
        e.description.toLowerCase().includes(q) ||
        e.category.toLowerCase().includes(q)
      )
    }
    return true
  })

  const totalPages  = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage    = Math.min(page, totalPages)
  const pageEntries = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const toggleRow = (id: string) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const allChecked = pageEntries.length > 0 && pageEntries.every(e => selected.has(e.id))
  const toggleAll  = () => {
    if (allChecked) {
      setSelected(prev => { const n = new Set(prev); pageEntries.forEach(e => n.delete(e.id)); return n })
    } else {
      setSelected(prev => { const n = new Set(prev); pageEntries.forEach(e => n.add(e.id)); return n })
    }
  }

  const handleFilterChange = (f: Filter) => { setFilter(f); setPage(1) }
  const handleSearch = (v: string)        => { setSearch(v); setPage(1) }

  /* Export handlers — stream file download via axios blob */
  const doExport = async (fmt: 'csv' | 'pdf') => {
    setExporting(fmt)
    try {
      const path = fmt === 'csv' ? '/ledger/export/csv' : '/ledger/export/pdf'
      const res  = await api.get(path, { responseType: 'blob' })
      const mime = fmt === 'csv' ? 'text/csv' : 'application/pdf'
      const ext  = fmt
      const url  = URL.createObjectURL(new Blob([res.data as BlobPart], { type: mime }))
      const a    = document.createElement('a')
      a.href = url
      a.download = `foid_ledger_${new Date().toISOString().slice(0, 10)}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // silently fail — user will see no download
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Ledger History</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            Every AI-generated ledger entry — searchable, editable, and exportable
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          <button
            onClick={() => doExport('csv')}
            disabled={exporting !== null || displayEntries.length === 0}
            className="flex items-center gap-2 px-4 py-2.5 border border-neutral-200 rounded-full text-[13px] font-semibold text-neutral-800 bg-white hover:bg-neutral-50 transition-colors disabled:opacity-40"
          >
            <RemixIcon name={exporting === 'csv' ? 'ri-loader-4-line' : 'ri-file-text-line'} size={16} color="#18181b" />
            {exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
          </button>
          <button
            onClick={() => doExport('pdf')}
            disabled={exporting !== null || displayEntries.length === 0}
            className="flex items-center gap-2 px-4 py-2.5 border border-neutral-200 rounded-full text-[13px] font-semibold text-neutral-800 bg-white hover:bg-neutral-50 transition-colors disabled:opacity-40"
          >
            <RemixIcon name={exporting === 'pdf' ? 'ri-loader-4-line' : 'ri-file-pdf-2-line'} size={16} color="#18181b" />
            {exporting === 'pdf' ? 'Preparing…' : 'Export PDF'}
          </button>
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Entries"
          value={loadingData ? '…' : String(displayStats?.total_entries ?? 0)}
          sub={displayStats?.total_entries ? 'Since your account began' : 'No entries yet — upload a receipt'}
          subColor="text-neutral-400" icon="ri-list-check-2" />
        <StatCard
          label="Auto-categorised"
          value={loadingData ? '…' : (displayStats?.total_entries ? `${displayStats.auto_categorised_pct}%` : '—')}
          sub={displayStats?.total_entries ? 'Without manual edits' : 'Awaiting first upload'}
          subColor="text-neutral-400" icon="ri-arrow-right-up-line" />
        <StatCard
          label="Exports This Month"
          value={loadingData ? '…' : String(displayStats?.exports_this_month ?? 0)}
          sub="CSV & PDF combined"
          subColor="text-neutral-400" icon="ri-bar-chart-grouped-line" />
        <StatCard
          label="History"
          value="Unlimited"
          sub="Full history kept, always"
          subColor="text-neutral-400" icon="ri-wallet-line" />
      </div>

      {/* ── Table card ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">

        {/* Filter tabs + search */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 pt-5 pb-4">
          <div className="flex items-center rounded-full p-1 shrink-0" style={{ background: '#f0f0f0' }}>
            {TABS.map(tab => (
              <button key={tab} onClick={() => handleFilterChange(tab)}
                className="px-4 sm:px-6 py-1.5 rounded-full text-[13px] font-medium transition-all whitespace-nowrap"
                style={
                  filter === tab
                    ? { background: '#fff', color: '#18181b', fontWeight: 700, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                    : { background: 'transparent', color: '#9a9a9a' }
                }>
                {tab}
              </button>
            ))}
          </div>
          <div className="relative w-full sm:w-[300px]">
            <RemixIcon name="ri-search-line" size={15} color="#a1a1aa"
              className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input type="text" value={search} onChange={e => handleSearch(e.target.value)}
              placeholder="Search description, category"
              className="w-full pl-9 pr-4 py-2 rounded-full border border-neutral-200 bg-neutral-50 text-[13px] text-neutral-800 placeholder:text-neutral-400 focus:outline-none focus:border-brand-400 transition-colors" />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse" style={{ minWidth: 820 }}>
            <thead>
              <tr className="border-y border-neutral-100" style={{ background: '#fafafa' }}>
                <th className="pl-6 pr-3 py-3.5 w-10">
                  <input type="checkbox" checked={allChecked} onChange={toggleAll}
                    className="w-4 h-4 rounded-full accent-[#c026d3]" />
                </th>
                {['DATE', 'DESCRIPTION', 'CATEGORY', 'TYPE', 'AMOUNT', 'SOURCE', 'CONFIDENCE', 'ACTIONS'].map(col => (
                  <th key={col}
                    className="px-3 py-3.5 text-[11.5px] font-bold text-neutral-500 uppercase tracking-widest whitespace-nowrap last:pr-6">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {pageEntries.map(entry => (
                <tr key={entry.id}
                  className={`transition-colors hover:bg-neutral-50/60 ${selected.has(entry.id) ? 'bg-[#fdf4ff]' : ''}`}>
                  <td className="pl-6 pr-3 py-4">
                    <input type="checkbox" checked={selected.has(entry.id)}
                      onChange={() => toggleRow(entry.id)} className="w-4 h-4 rounded-full accent-[#c026d3]" />
                  </td>
                  <td className="px-3 py-4 text-[13px] font-semibold text-neutral-800 whitespace-nowrap">
                    {new Date(entry.entry_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </td>
                  <td className="px-3 py-4 text-[13px] text-neutral-700 max-w-[200px] leading-snug">{entry.description}</td>
                  <td className="px-3 py-4"><CategoryPill label={entry.category} /></td>
                  <td className="px-3 py-4 text-[13px] text-neutral-600 capitalize">{entry.entry_type}</td>
                  <td className="px-3 py-4 text-[13px] font-semibold whitespace-nowrap"
                    style={{ color: entry.entry_type === 'income' ? '#16a34a' : '#dc2626' }}>
                    {entry.entry_type === 'income' ? '+' : '-'}{naira(parseFloat(entry.amount))}
                  </td>
                  <td className="px-3 py-4">
                    <div className="flex items-center gap-1.5 text-[13px] text-neutral-600">
                      <RemixIcon name={SOURCE_ICON[entry.source.toLowerCase()] ?? 'ri-file-line'} size={14} color="#a1a1aa" />
                      {entry.source}
                    </div>
                  </td>
                  <td className="px-3 py-4 text-[13px] text-neutral-600 whitespace-nowrap">
                    {Math.round(entry.confidence * 100)}%
                  </td>
                  <td className="px-3 py-4 pr-6">
                    <button className="flex items-center gap-1 text-[13px] font-semibold text-neutral-600 hover:text-brand-500 transition-colors">
                      <RemixIcon name="ri-pencil-line" size={13} color="currentColor" />
                      Edit
                    </button>
                  </td>
                </tr>
              ))}

              {!loadingData && pageEntries.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <RemixIcon name="ri-file-list-3-line" size={36} color="#d4d4d8" />
                      <p className="text-[14px] font-semibold text-neutral-500">
                        {displayEntries.length === 0 ? 'No ledger entries yet' : 'No entries match your filter'}
                      </p>
                      <p className="text-[13px] text-neutral-400">
                        {displayEntries.length === 0
                          ? 'Head to the Business Ledger page and upload a receipt to get started'
                          : 'Try clearing the search or switching filter tabs'}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
              {loadingData && (
                <tr>
                  <td colSpan={9} className="px-6 py-10 text-center text-[13px] text-neutral-400">Loading…</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-t border-neutral-100">
          <span className="text-[13px] text-neutral-600">
            Showing <span className="font-semibold text-neutral-900">{pageEntries.length}</span>
            {' '}of <span className="font-semibold text-neutral-900">{filtered.length}</span> entries
            {filter !== 'All' || search ? ` (${displayEntries.length} total)` : ''}
          </span>
          <div className="flex items-center gap-1.5">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}
              className="w-8 h-8 flex items-center justify-center rounded-full border border-neutral-200 text-neutral-500 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
              <RemixIcon name="ri-arrow-left-s-line" size={16} color="currentColor" />
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map(p => (
              <button key={p} onClick={() => setPage(p)}
                className="w-8 h-8 flex items-center justify-center rounded-full text-[13px] font-semibold transition-colors"
                style={safePage === p ? { background: '#c026d3', color: '#fff' } : { background: 'transparent', color: '#71717a' }}>
                {p}
              </button>
            ))}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}
              className="w-8 h-8 flex items-center justify-center rounded-full border border-neutral-200 text-neutral-500 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
              <RemixIcon name="ri-arrow-right-s-line" size={16} color="currentColor" />
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
