import { useEffect, useRef, useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import type { LedgerEntry } from '@/types/foid'

/* ── Helpers ─────────────────────────────────────────────────────────── */
const naira = (n: number) => '₦' + Math.abs(n).toLocaleString('en-NG', { maximumFractionDigits: 0 })

/* ── Mock data shown to unverified users (preview mode) ─────────────── */
const MOCK_ENTRIES: LedgerEntry[] = [
  { id: 'm1', entry_date: '2026-07-14', description: 'Uber fleet — weekly delivery run',          category: 'Logistics', entry_type: 'expense', amount: '48200',  source: 'receipt', confidence: 0.98, raw_file_path: null, created_at: '' },
  { id: 'm2', entry_date: '2026-07-13', description: 'Client payment — Studio Kola invoice #114', category: 'Sales',     entry_type: 'income',  amount: '320000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm3', entry_date: '2026-07-12', description: 'Notion + Figma team subscription',          category: 'Software',  entry_type: 'expense', amount: '31500',  source: 'receipt', confidence: 0.96, raw_file_path: null, created_at: '' },
  { id: 'm4', entry_date: '2026-07-11', description: 'Staff payroll — July first tranche',        category: 'Payroll',   entry_type: 'expense', amount: '640000', source: 'bank',    confidence: 0.99, raw_file_path: null, created_at: '' },
  { id: 'm5', entry_date: '2026-07-10', description: 'Facebook + Google Ads — Q3 sprint',         category: 'Marketing', entry_type: 'expense', amount: '140700', source: 'invoice', confidence: 0.94, raw_file_path: null, created_at: '' },
  { id: 'm6', entry_date: '2026-07-09', description: 'Client retainer — Vance Studios',           category: 'Sales',     entry_type: 'income',  amount: '180000', source: 'invoice', confidence: 1.00, raw_file_path: null, created_at: '' },
  { id: 'm7', entry_date: '2026-07-08', description: 'Office supplies & stationery',              category: 'Other',     entry_type: 'expense', amount: '74000',  source: 'receipt', confidence: 0.87, raw_file_path: null, created_at: '' },
]
const MOCK_STATS = { total_income: 2140500, total_expense: 1382900, net: 757600, estimated_tax: 56820 }

/* ── Spend categories for right-side panel ───────────────────────────── */
const DONUT_PALETTE = ['#c026d3', '#e879f9', '#d4d4d8', '#a855f7', '#f0abfc']
const GAP_DEG = 3

interface CatTotal { label: string; amount: number }

function SpendDonut({ cats, total }: { cats: CatTotal[]; total: number }) {
  const SIZE = 200, CX = 100, CY = 100, R = 74, SW = 18
  const circ = 2 * Math.PI * R

  const segs = cats.slice(0, 5).map((c, i) => ({
    color: DONUT_PALETTE[i],
    pct: total > 0 ? Math.round((c.amount / total) * 100) : 0,
  }))

  let cursor = -90
  const built = segs.map(s => {
    const spanDeg = (s.pct / 100) * 360 - GAP_DEG
    const entry = { ...s, startDeg: cursor + GAP_DEG / 2, spanDeg: Math.max(spanDeg, 0) }
    cursor += (s.pct / 100) * 360
    return entry
  })

  const toArc = (deg: number) => {
    const frac = deg / 360
    return `${frac * circ} ${circ - frac * circ}`
  }

  if (total === 0) {
    return (
      <div className="relative mx-auto flex items-center justify-center"
        style={{ width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
          <circle cx={CX} cy={CY} r={R} fill="none" stroke="#f4f4f5" strokeWidth={SW} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <div className="text-[22px] font-extrabold text-neutral-300 leading-none">₦0</div>
          <div className="text-[11px] text-neutral-400 mt-1">total spend</div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative mx-auto" style={{ width: SIZE, height: SIZE }}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <circle cx={CX} cy={CY} r={R} fill="none" stroke="#f4f4f5" strokeWidth={SW} />
        {built.map((s, i) => (
          <circle key={i} cx={CX} cy={CY} r={R} fill="none"
            stroke={s.color} strokeWidth={SW} strokeLinecap="round"
            strokeDasharray={toArc(s.spanDeg)}
            transform={`rotate(${s.startDeg} ${CX} ${CY})`} />
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="text-[22px] font-extrabold text-neutral-900 leading-none">{naira(total)}</div>
        <div className="text-[11px] text-neutral-400 mt-1">total spend</div>
      </div>
    </div>
  )
}

function CatRow({ label, amount, max }: { label: string; amount: number; max: number }) {
  const pct = max > 0 ? Math.round((amount / max) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-[13px] font-semibold text-neutral-800 w-[80px] shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-neutral-100 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: '#c026d3' }} />
      </div>
      <span className="text-[13px] font-semibold text-neutral-800 w-[80px] text-right shrink-0">{naira(amount)}</span>
    </div>
  )
}

function SourceIcon({ source }: { source: string }) {
  const map: Record<string, string> = {
    receipt: 'ri-receipt-line', invoice: 'ri-file-text-line', bank: 'ri-bank-line',
  }
  return <RemixIcon name={map[source.toLowerCase()] ?? 'ri-file-line'} size={14} color="#a1a1aa" />
}

const CAT_COLORS: Record<string, { bg: string; color: string }> = {
  Logistics: { bg: '#eff6ff', color: '#2563eb' }, Sales:     { bg: '#f0fdf4', color: '#16a34a' },
  Software:  { bg: '#faf5ff', color: '#7c3aed' }, Payroll:   { bg: '#fae8ff', color: '#c026d3' },
  Marketing: { bg: '#fff7ed', color: '#c2410c' }, Other:     { bg: '#f4f4f5', color: '#71717a' },
  Utilities: { bg: '#fefce8', color: '#92400e' },
}
function CategoryPill({ label }: { label: string }) {
  const c = CAT_COLORS[label] ?? { bg: '#f4f4f5', color: '#71717a' }
  return (
    <span className="inline-flex px-2.5 py-1 rounded-full text-[11.5px] font-semibold whitespace-nowrap"
      style={{ background: c.bg, color: c.color }}>{label}</span>
  )
}

interface Stats {
  total_income: number; total_expense: number; net: number; estimated_tax: number
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
const PAGE_SIZE = 5

export default function BusinessLedger() {
  const { user } = useAuth()
  const isVerified = user?.email_verified ?? false

  const [entries, setEntries]     = useState<LedgerEntry[]>([])
  const [stats, setStats]         = useState<Stats | null>(null)
  const [loadingData, setLoading] = useState(true)
  const [dragging, setDragging]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [selected, setSelected]   = useState<Set<string>>(new Set())
  const [page, setPage]           = useState(1)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    if (!isVerified) { setLoading(false); return }
    setLoading(true)
    try {
      const [entriesRes, statsRes] = await Promise.all([
        api.get<LedgerEntry[]>('/ledger', { params: { limit: 100 } }),
        api.get<Stats>('/ledger/stats'),
      ])
      setEntries(entriesRes.data)
      setStats(statsRes.data)
    } catch {
      // leave empty
    } finally {
      setLoading(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [isVerified])

  const toggleRow = (id: string) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  // ── Upload handler ───────────────────────────────────────────────────
  const doUpload = async (file: File) => {
    setUploadError(null)
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      await api.post('/ledger/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      await load()   // refresh table + stats after successful scan
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string }; status?: number } }
      if (axiosErr.response?.status === 402) {
        setUploadError('Insufficient AI credits. Top up in the AI Credit Wallet.')
      } else {
        setUploadError(axiosErr.response?.data?.detail ?? 'Upload failed. Please try again.')
      }
    } finally {
      setUploading(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) { doUpload(file); e.target.value = '' }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) doUpload(file)
  }

  // ── Use mock data for unverified users ───────────────────────────────
  const displayEntries = isVerified ? entries : MOCK_ENTRIES
  const displayStats   = isVerified ? stats   : MOCK_STATS

  const totalPages  = Math.max(1, Math.ceil(displayEntries.length / PAGE_SIZE))
  const pageEntries = displayEntries.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // ── Spend categories derived from entries ────────────────────────────
  const catMap: Record<string, number> = {}
  for (const e of displayEntries) {
    if (e.entry_type === 'expense') {
      const n = parseFloat(e.amount)
      catMap[e.category] = (catMap[e.category] ?? 0) + n
    }
  }
  const cats: CatTotal[] = Object.entries(catMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, amount]) => ({ label, amount }))
  const catMax = cats[0]?.amount ?? 0
  const totalSpend = cats.reduce((s, c) => s + c.amount, 0)

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Business Ledger</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            Snap a receipt, forward an invoice, or just ask — FOID's AI keeps your books for you
          </p>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full font-semibold text-[14px] text-white transition-opacity hover:opacity-90 disabled:opacity-50 shrink-0 self-start"
          style={{ background: '#c026d3' }}
        >
          <RemixIcon name={uploading ? 'ri-loader-4-line' : 'ri-camera-fill'} size={18} color="#fff" />
          {uploading ? 'Scanning…' : 'Scan receipt'}
        </button>
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf"
          className="hidden" onChange={handleFileChange} />
      </div>

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Income (MTD)"
          value={loadingData ? '…' : naira(displayStats?.total_income ?? 0)}
          sub={displayStats && displayStats.total_income > 0 ? 'From receipts & invoices' : 'Upload receipts to track income'}
          subColor="text-brand-500 font-semibold" icon="ri-arrow-left-down-long-line" />
        <StatCard label="Total Expenses (MTD)"
          value={loadingData ? '…' : naira(displayStats?.total_expense ?? 0)}
          sub={displayStats && displayStats.total_income > 0 ? `${Math.round(((displayStats.total_expense ?? 0) / displayStats.total_income) * 100)}% of income` : 'No expenses recorded yet'}
          subColor="text-neutral-400" icon="ri-arrow-right-up-long-line" />
        <StatCard label="Net Profit"
          value={loadingData ? '…' : naira(displayStats?.net ?? 0)}
          sub={displayStats && displayStats.net !== 0 ? (displayStats.net >= 0 ? '↗ Positive cash flow' : '↘ Expenses exceed income') : 'No data yet'}
          subColor={displayStats && displayStats.net >= 0 ? 'text-brand-500 font-semibold' : 'text-red-500 font-semibold'} icon="ri-bar-chart-fill" />
        <StatCard label="Estimated Tax (7.5%)"
          value={loadingData ? '…' : naira(displayStats?.estimated_tax ?? 0)}
          sub="Set aside for this quarter" subColor="text-neutral-400" icon="ri-bank-fill" />
      </div>

      {/* ── Middle row: upload zone + spend breakdown ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Upload zone */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[15px] font-bold text-neutral-900">Add a record</div>
              <div className="text-[12.5px] text-neutral-400 mt-0.5">Upload a receipt, invoice, or bank statement — AI does the rest</div>
            </div>
            <span className="text-[11.5px] font-semibold px-3 py-1 rounded-full shrink-0"
              style={{ background: '#fae8ff', color: '#c026d3' }}>~4 credits / scan</span>
          </div>

          {uploadError && (
            <div className="text-[13px] text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-3">
              {uploadError}
            </div>
          )}

          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => !uploading && fileInputRef.current?.click()}
            className="flex-1 flex flex-col items-center justify-center gap-3 rounded-2xl py-12 transition-colors cursor-pointer"
            style={{
              border: `2px dashed ${dragging ? '#c026d3' : '#e879f9'}`,
              background: dragging ? '#fdf4ff' : '#fdf4ff',
              minHeight: 260,
            }}
          >
            {uploading ? (
              <>
                <RemixIcon name="ri-loader-4-line" size={64} color="#c026d3" />
                <p className="text-[14px] font-semibold text-neutral-700">AI is reading your receipt…</p>
                <p className="text-[12px] text-neutral-400">This takes a few seconds</p>
              </>
            ) : (
              <>
                <RemixIcon name="ri-upload-cloud-2-line" size={84} color="#c026d3" />
                <div className="text-center">
                  <p className="text-[14px] text-neutral-700">
                    <span className="font-bold text-neutral-900">Drop a file here</span> or click to browse
                  </p>
                  <p className="text-[12px] text-neutral-400 mt-1">JPG, PNG, PDF up to 10MB — receipts, invoices, statements</p>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); fileInputRef.current?.click() }}
                  className="mt-1 px-6 py-2.5 rounded-full text-[14px] font-bold text-white transition-opacity hover:opacity-90"
                  style={{ background: '#c026d3' }}
                >
                  Upload Image
                </button>
              </>
            )}
          </div>
        </div>

        {/* Spend breakdown */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5 flex flex-col gap-5">
          <div className="text-[15px] font-bold text-neutral-900">Spending breakdown</div>
          <SpendDonut cats={cats} total={totalSpend} />
          {cats.length > 0 ? (
            <div className="flex flex-col gap-3 mt-1">
              {cats.map(c => <CatRow key={c.label} label={c.label} amount={c.amount} max={catMax} />)}
            </div>
          ) : (
            <p className="text-[13px] text-neutral-400 text-center py-4">
              No expenses yet — upload a receipt to see your spending breakdown
            </p>
          )}
        </div>
      </div>

      {/* ── Latest AI-categorised entries table ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">
        <div className="flex items-start justify-between px-6 pt-5 pb-3 gap-4">
          <div>
            <div className="text-[15px] font-bold text-neutral-900">Latest AI-categorised entries</div>
            <div className="text-[12px] text-neutral-400 mt-0.5">Auto-extracted from uploaded documents</div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse" style={{ minWidth: 780 }}>
            <thead>
              <tr className="border-y border-neutral-100 bg-neutral-50">
                <th className="pl-6 pr-3 py-3 w-10">
                  <input type="checkbox" className="accent-[#c026d3] w-4 h-4 rounded" readOnly />
                </th>
                {['DATE', 'DESCRIPTION', 'CATEGORY', 'TYPE', 'AMOUNT', 'SOURCE', 'CONFIDENCE'].map(col => (
                  <th key={col} className="px-3 py-3 text-[11px] font-bold text-neutral-400 uppercase tracking-widest whitespace-nowrap last:pr-6">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {pageEntries.map(entry => (
                <tr key={entry.id}
                  className={`hover:bg-neutral-50/60 transition-colors ${selected.has(entry.id) ? 'bg-brand-50' : ''}`}>
                  <td className="pl-6 pr-3 py-4">
                    <input type="checkbox" checked={selected.has(entry.id)}
                      onChange={() => toggleRow(entry.id)} className="accent-[#c026d3] w-4 h-4 rounded" />
                  </td>
                  <td className="px-3 py-4 text-[13px] text-neutral-500 whitespace-nowrap">
                    {new Date(entry.entry_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </td>
                  <td className="px-3 py-4 text-[13px] font-medium text-neutral-800 max-w-[200px]">{entry.description}</td>
                  <td className="px-3 py-4"><CategoryPill label={entry.category} /></td>
                  <td className="px-3 py-4 text-[13px] text-neutral-600 capitalize">{entry.entry_type}</td>
                  <td className="px-3 py-4 text-[13px] font-semibold whitespace-nowrap"
                    style={{ color: entry.entry_type === 'income' ? '#16a34a' : '#dc2626' }}>
                    {entry.entry_type === 'income' ? '+' : '-'}{naira(parseFloat(entry.amount))}
                  </td>
                  <td className="px-3 py-4">
                    <div className="flex items-center gap-1.5 text-[12.5px] text-neutral-500">
                      <SourceIcon source={entry.source} />{entry.source}
                    </div>
                  </td>
                  <td className="px-3 py-4 text-[13px] text-neutral-600 whitespace-nowrap pr-6">
                    {Math.round(entry.confidence * 100)}%
                  </td>
                </tr>
              ))}
              {!loadingData && pageEntries.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-14 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <RemixIcon name="ri-file-add-line" size={36} color="#d4d4d8" />
                      <p className="text-[14px] font-semibold text-neutral-500">No entries yet</p>
                      <p className="text-[13px] text-neutral-400">Upload a receipt above and the AI will extract and categorise it automatically</p>
                    </div>
                  </td>
                </tr>
              )}
              {loadingData && (
                <tr><td colSpan={8} className="px-6 py-10 text-center text-[13px] text-neutral-400">Loading…</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-6 py-4 border-t border-neutral-100">
          <span className="text-[13px] text-neutral-500">
            Showing <span className="font-semibold text-neutral-800">{pageEntries.length}</span> of{' '}
            <span className="font-semibold text-neutral-800">{displayEntries.length}</span> entries
          </span>
          <div className="flex items-center gap-1.5">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="w-8 h-8 flex items-center justify-center rounded-full border border-neutral-200 text-neutral-500 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
              <RemixIcon name="ri-arrow-left-s-line" size={16} color="currentColor" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).slice(0, 5).map(p => (
              <button key={p} onClick={() => setPage(p)}
                className="w-8 h-8 flex items-center justify-center rounded-full text-[13px] font-semibold transition-colors"
                style={page === p ? { background: '#c026d3', color: '#fff' } : { background: 'transparent', color: '#71717a' }}>
                {p}
              </button>
            ))}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="w-8 h-8 flex items-center justify-center rounded-full border border-neutral-200 text-neutral-500 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
              <RemixIcon name="ri-arrow-right-s-line" size={16} color="currentColor" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
