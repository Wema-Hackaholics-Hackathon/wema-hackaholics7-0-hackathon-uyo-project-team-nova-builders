import { useCallback, useState } from 'react'
import StatCard from '@/components/StatCard'
import RemixIcon from '@/components/RemixIcon'
import { useAuth } from '@/contexts/AuthContext'
import { useMonoData } from '@/hooks/useMonoData'
import { api } from '@/lib/api'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'

/* ── Colours ────────────────────────────────────────────────────────── */
const BRAND      = '#c026d3'
const BRAND_LITE = '#f5d0fe'
const PINK       = '#e879f9'

/* ── Helpers ────────────────────────────────────────────────────────── */
const naira = (n: number) => '₦' + n.toLocaleString('en-NG')

/* ── Page ───────────────────────────────────────────────────────────── */
export default function ReportsPage() {
  const { user } = useAuth()
  const isVerified = user?.email_verified ?? false
  const { monthlyRows, chartData, spendByCategory, totalCredit, totalDebit, loading } = useMonoData(isVerified)

  const [exportingCSV, setExportingCSV]   = useState(false)
  const [exportingPDF, setExportingPDF]   = useState(false)
  const [downloadingMonthly, setDownloadingMonthly] = useState<string | null>(null)

  /* ── Aggregates ── */
  const last6 = monthlyRows.slice(0, 6)
  const avgIncome  = last6.length > 0 ? Math.round(last6.reduce((s, r) => s + r.income, 0) / last6.length) : 0
  const avgExpense = last6.length > 0 ? Math.round(last6.reduce((s, r) => s + r.expense, 0) / last6.length) : 0
  const netCashFlow = totalCredit - totalDebit
  const savingsRate = avgIncome > 0 ? Math.round(((avgIncome - avgExpense) / avgIncome) * 100) : 0

  /* ── Income sources from spend categories (credit side ≈ income type) ── */
  // We don't have income-side categories from Mono; use spend category names as proxy
  const incomeSourcesData = spendByCategory.slice(0, 3).map(c => ({
    source: c.label,
    amount: c.value,
  }))

  /* ── Export handlers ── */
  const handleExportCSV = useCallback(async () => {
    if (exportingCSV) return
    setExportingCSV(true)
    try {
      const res = await api.get('/reports/export/csv', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `foid_report_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* silently ignore */ }
    finally { setExportingCSV(false) }
  }, [exportingCSV])

  const handleExportPDF = useCallback(async () => {
    if (exportingPDF) return
    setExportingPDF(true)
    try {
      const res = await api.get('/reports/export/pdf', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `foid_report_${new Date().toISOString().slice(0, 10)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* silently ignore */ }
    finally { setExportingPDF(false) }
  }, [exportingPDF])

  const handleDownloadMonthly = useCallback(async (ym: string) => {
    if (downloadingMonthly) return
    setDownloadingMonthly(ym)
    try {
      const res = await api.get('/reports/monthly-pdf', {
        params: { month: ym },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `foid_audit_${ym}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* silently ignore */ }
    finally { setDownloadingMonthly(null) }
  }, [downloadingMonthly])

  /* ── Chart data for area chart ── */
  // Use Mono daily data if available, else show no chart
  const areaData = chartData.length > 0
    ? chartData.map(d => ({ x: d.week, income: d.income, expense: d.expense }))
    : []

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Reports & Insights</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            A closer look at your cash flow, spending patterns, and tax position
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          <button
            onClick={() => void handleExportCSV()}
            disabled={exportingCSV}
            className="flex items-center gap-2 px-5 py-2.5 border border-neutral-200 rounded-full font-semibold text-[13px] text-neutral-800 bg-white hover:bg-neutral-50 transition-colors disabled:opacity-60"
          >
            {exportingCSV
              ? <RemixIcon name="ri-loader-4-line" size={16} color="#18181b" className="animate-spin" />
              : <RemixIcon name="ri-file-text-line" size={16} color="#18181b" />
            }
            {exportingCSV ? 'Exporting…' : 'Export CSV'}
          </button>
          <button
            onClick={() => void handleExportPDF()}
            disabled={exportingPDF}
            className="flex items-center gap-2 px-5 py-2.5 border border-neutral-200 rounded-full font-semibold text-[13px] text-neutral-800 bg-white hover:bg-neutral-50 transition-colors disabled:opacity-60"
          >
            {exportingPDF
              ? <RemixIcon name="ri-loader-4-line" size={16} color="#18181b" className="animate-spin" />
              : <RemixIcon name="ri-file-pdf-2-line" size={16} color="#18181b" />
            }
            {exportingPDF ? 'Exporting…' : 'Export PDF'}
          </button>
        </div>
      </div>

      {/* ── Stat cards (live Mono aggregates) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Net Cash Flow"
          value={loading ? '…' : naira(netCashFlow)}
          sub={netCashFlow >= 0 ? '↗ Positive cash flow' : '↘ Net outflow'}
          subColor={netCashFlow >= 0 ? 'text-brand-500 font-semibold' : 'text-red-500 font-semibold'}
          icon="ri-bar-chart-fill"
        />
        <StatCard
          label="Avg. Monthly Income"
          value={loading ? '…' : (avgIncome > 0 ? naira(avgIncome) : '—')}
          sub={`Last ${last6.length || 6} months`}
          subColor="text-neutral-400"
          icon="ri-arrow-left-down-long-line"
        />
        <StatCard
          label="Avg. Monthly Expense"
          value={loading ? '…' : (avgExpense > 0 ? naira(avgExpense) : '—')}
          sub={`Last ${last6.length || 6} months`}
          subColor="text-neutral-400"
          icon="ri-arrow-up-right-line"
        />
        <StatCard
          label="Savings Rate"
          value={loading ? '…' : (savingsRate > 0 ? `${savingsRate}%` : '—')}
          sub="Income minus expenses"
          subColor="text-brand-500 font-semibold"
          icon="ri-wallet-line"
        />
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5">

        {/* Income vs expenses — area chart (Mono daily data) */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="font-bold text-[15px] text-neutral-900 mb-0.5">Income vs. expenses</div>
          <div className="text-[12px] text-neutral-400 mb-4">
            {areaData.length > 0
              ? `Last ${areaData.length} days across all connected banks`
              : 'Connect a bank to see real transaction data'}
          </div>
          {areaData.length === 0 && !loading && (
            <div className="flex items-center justify-center h-[300px] text-[13px] text-neutral-400">
              No transaction data yet — connect a bank via Mono to populate this chart.
            </div>
          )}
          {loading && (
            <div className="flex items-center justify-center h-[300px] text-[13px] text-neutral-400">
              <RemixIcon name="ri-loader-4-line" size={20} color="#a1a1aa" className="mr-2 animate-spin" />
              Loading…
            </div>
          )}
          {areaData.length > 0 && (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={areaData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="rGradIncome" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={BRAND}      stopOpacity={0.25} />
                    <stop offset="95%" stopColor={BRAND}      stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="rGradExpense" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={BRAND_LITE} stopOpacity={0.45} />
                    <stop offset="95%" stopColor={BRAND_LITE} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
                <XAxis dataKey="x" tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `₦${v >= 1000 ? Math.round(v / 1000) + 'k' : v}`}
                  width={52}
                />
                <Tooltip
                  formatter={(val, name) => [naira(Number(val)), name === 'income' ? 'Income' : 'Expenses']}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e4e4e7' }}
                />
                <Area type="monotone" dataKey="income"
                  stroke={BRAND} strokeWidth={2} fill="url(#rGradIncome)"
                  dot={{ r: 3, fill: '#fff', stroke: BRAND, strokeWidth: 2 }}
                  activeDot={{ r: 4, fill: BRAND }}
                />
                <Area type="monotone" dataKey="expense"
                  stroke={PINK} strokeWidth={2} fill="url(#rGradExpense)"
                  dot={{ r: 3, fill: '#fff', stroke: PINK, strokeWidth: 2 }}
                  activeDot={{ r: 4, fill: PINK }}
                />
                <Legend verticalAlign="bottom" align="right" iconType="circle" iconSize={10}
                  wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
                  formatter={(value) => (
                    <span style={{ color: '#71717a' }}>
                      {value === 'income' ? 'Income' : 'Expenses'}
                    </span>
                  )}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Spend by category — bar chart (replaces "Income Sources") */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="font-bold text-[15px] text-neutral-900 mb-1">Top Spend Categories</div>
          <div className="text-[12px] text-neutral-400 mb-4">By debit volume from Mono transactions</div>
          {incomeSourcesData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={incomeSourcesData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barSize={60} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
                <XAxis dataKey="source" tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `₦${v >= 1000 ? Math.round(v / 1000) + 'k' : v}`}
                  width={52}
                />
                <Tooltip
                  formatter={(val) => [naira(Number(val)), 'Amount']}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e4e4e7' }}
                />
                <Bar dataKey="amount" fill={BRAND} radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[300px] text-[13px] text-neutral-400">
              {loading ? (
                <RemixIcon name="ri-loader-4-line" size={20} color="#a1a1aa" className="animate-spin" />
              ) : 'No spend data yet'}
            </div>
          )}
        </div>

      </div>

      {/* ── Monthly summary table (live Mono aggregates) ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-5 border-b border-neutral-100">
          <div className="font-bold text-[15px] text-neutral-900">Monthly summary</div>
          <div className="text-[12px] text-neutral-400 mt-0.5">Computed from Mono Open Banking transactions</div>
        </div>

        {loading && (
          <div className="px-6 py-10 text-center text-[13px] text-neutral-400">
            <RemixIcon name="ri-loader-4-line" size={20} color="#a1a1aa" className="mx-auto mb-2 animate-spin" />
            Loading…
          </div>
        )}

        {!loading && monthlyRows.length === 0 && (
          <div className="px-6 py-10 text-center text-[13px] text-neutral-400">
            No monthly data yet — connect a bank and Mono will populate this table.
          </div>
        )}

        {!loading && monthlyRows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-neutral-100">
                  {['MONTH', 'INCOME', 'EXPENSES', 'NET', 'EST. TAX', 'ACTIONS'].map((col, i, arr) => (
                    <th key={col}
                      className={[
                        'px-6 py-4 text-[11px] font-bold text-neutral-400 uppercase tracking-widest whitespace-nowrap',
                        i === 0              ? 'rounded-tl-xl' : '',
                        i === arr.length - 1 ? 'rounded-tr-xl' : '',
                      ].join(' ')}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {monthlyRows.map((row, i) => (
                  <tr key={i} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/60 transition-colors">
                    <td className="px-6 py-5 text-[14px] font-semibold text-neutral-900">{row.month}</td>
                    <td className="px-6 py-5 text-[13px] text-neutral-700">{naira(row.income)}</td>
                    <td className="px-6 py-5 text-[13px] text-neutral-700">{naira(row.expense)}</td>
                    <td className="px-6 py-5 text-[13px]"
                      style={{ color: row.net >= 0 ? '#16a34a' : '#dc2626' }}>
                      {naira(row.net)}
                    </td>
                    <td className="px-6 py-5 text-[13px] text-neutral-700">{naira(row.tax)}</td>
                    <td className="px-6 py-5">
                      <button
                        onClick={() => void handleDownloadMonthly(row.year_month)}
                        disabled={downloadingMonthly === row.year_month}
                        className="flex items-center gap-2 px-4 py-1.5 border border-neutral-200 rounded-full text-[12px] font-semibold text-neutral-700 hover:bg-neutral-50 transition-colors disabled:opacity-60"
                      >
                        {downloadingMonthly === row.year_month
                          ? <RemixIcon name="ri-loader-4-line" size={14} color="#52525b" className="animate-spin" />
                          : <RemixIcon name="ri-download-fill" size={14} color="#52525b" />
                        }
                        {downloadingMonthly === row.year_month ? 'Preparing…' : 'Download'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  )
}
