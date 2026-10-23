/**
 * useMonoData
 *
 * Fetches all connected banks + their transactions from the backend,
 * then computes the aggregates every page needs:
 *
 *   - monthlyRows   — [{month, income, expense, net, tax}, ...] newest-first
 *   - mtd           — current calendar-month totals
 *   - chartData     — [{week, income, expense}, ...] for the IncomeExpenseChart
 *   - spendByCategory — [{label, amount, value}, ...] sorted descending
 *   - totalCredit / totalDebit across all-time
 *   - banks         — raw ConnectedBank[]
 *   - loading / error
 *
 * Amounts are always in NAIRA (kobo ÷ 100).
 * Called with `verified` flag; returns empty aggregates when false.
 */

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import type { ConnectedBank, MonoTransaction } from '@/types/foid'

/* ── Output types ──────────────────────────────────────────────────── */

export interface MonthlyRow {
  month: string       // e.g. "Jul 2026"
  year_month: string  // e.g. "2026-07"
  income: number
  expense: number
  net: number
  tax: number
}

export interface ChartPoint {
  week: string        // e.g. "Week 1"
  income: number
  expense: number
}

export interface SpendCategory {
  label: string
  amount: string      // pre-formatted "₦640,000"
  value: number       // raw naira
}

export interface MtdTotals {
  income: number
  expense: number
  net: number
  tax: number
}

export interface MonoDataResult {
  banks: ConnectedBank[]
  monthlyRows: MonthlyRow[]
  mtd: MtdTotals
  chartData: ChartPoint[]
  spendByCategory: SpendCategory[]
  totalCredit: number
  totalDebit: number
  loading: boolean
  error: string
  reload: () => void
}

/* ── Helpers ───────────────────────────────────────────────────────── */

const nairaFmt = (n: number) =>
  '₦' + n.toLocaleString('en-NG', { minimumFractionDigits: 0, maximumFractionDigits: 0 })

function koboToNaira(k: number) { return k / 100 }

function monthLabel(ym: string): string {
  // ym = "YYYY-MM"
  try {
    const [y, m] = ym.split('-')
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-NG', { month: 'short', year: 'numeric' })
  } catch { return ym }
}

const TAX_RATE = 0.075

/* ── Hook ─────────────────────────────────────────────────────────── */

export function useMonoData(verified: boolean): MonoDataResult {
  const [banks, setBanks] = useState<ConnectedBank[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // All transactions across all banks, flat list
  const [allTx, setAllTx] = useState<MonoTransaction[]>([])

  const load = useCallback(async () => {
    if (!verified) return
    setLoading(true)
    setError('')
    try {
      const banksRes = await api.get<ConnectedBank[]>('/banks/connected')
      const fetchedBanks = banksRes.data
      setBanks(fetchedBanks)

      if (fetchedBanks.length === 0) {
        setAllTx([])
        return
      }

      // Fetch transactions for every bank in parallel, up to 200 each
      const txResults = await Promise.allSettled(
        fetchedBanks.map(b =>
          api.get<MonoTransaction[]>(`/banks/${b.id}/transactions`, { params: { limit: 200 } })
        )
      )

      const combined: MonoTransaction[] = []
      txResults.forEach(r => {
        if (r.status === 'fulfilled') combined.push(...r.value.data)
      })

      // Sort newest first by date
      combined.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      setAllTx(combined)
    } catch {
      setError('Could not load bank transaction data.')
    } finally {
      setLoading(false)
    }
  }, [verified])

  useEffect(() => { void load() }, [load])

  /* ── Aggregation ────────────────────────────────────────────────── */

  // Group by YYYY-MM, naira amounts
  const monthlyMap = new Map<string, { income: number; expense: number }>()
  for (const tx of allTx) {
    const ym = tx.date.slice(0, 7) // "YYYY-MM"
    if (!monthlyMap.has(ym)) monthlyMap.set(ym, { income: 0, expense: 0 })
    const bucket = monthlyMap.get(ym)!
    const naira = koboToNaira(tx.amount)
    if (tx.type === 'credit') bucket.income += naira
    else bucket.expense += naira
  }

  const monthlyRows: MonthlyRow[] = Array.from(monthlyMap.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))   // newest first
    .map(([ym, d]) => {
      const net = d.income - d.expense
      return {
        month: monthLabel(ym),
        year_month: ym,
        income: Math.round(d.income),
        expense: Math.round(d.expense),
        net: Math.round(net),
        tax: Math.round(Math.max(0, net * TAX_RATE)),
      }
    })

  // MTD — current calendar month
  const currentYM = new Date().toISOString().slice(0, 7)
  const mtdRow = monthlyMap.get(currentYM) ?? { income: 0, expense: 0 }
  const mtdNet = mtdRow.income - mtdRow.expense
  const mtd: MtdTotals = {
    income:  Math.round(koboToNaira(0) + mtdRow.income),
    expense: Math.round(mtdRow.expense),
    net:     Math.round(mtdNet),
    tax:     Math.round(Math.max(0, mtdNet * TAX_RATE)),
  }

  // Chart data — last 7 days bucketed by day, labelled "Day 1" … "Day 7"
  // We take the 7 most recent distinct calendar dates with data, then label them.
  const dayMap = new Map<string, { income: number; expense: number }>()
  for (const tx of allTx) {
    const day = tx.date.slice(0, 10)
    if (!dayMap.has(day)) dayMap.set(day, { income: 0, expense: 0 })
    const b = dayMap.get(day)!
    const n = koboToNaira(tx.amount)
    if (tx.type === 'credit') b.income += n
    else b.expense += n
  }
  const sortedDays = Array.from(dayMap.keys()).sort().slice(-7)
  const chartData: ChartPoint[] = sortedDays.map((d, i) => {
    const b = dayMap.get(d)!
    return {
      week: `Day ${i + 1}`,
      income: Math.round(b.income),
      expense: Math.round(b.expense),
    }
  })

  // Spend by category (debit only)
  const catMap = new Map<string, number>()
  for (const tx of allTx) {
    if (tx.type === 'debit') {
      const cat = tx.category && tx.category !== 'unknown' ? tx.category : 'Other'
      catMap.set(cat, (catMap.get(cat) ?? 0) + koboToNaira(tx.amount))
    }
  }
  const spendByCategory: SpendCategory[] = Array.from(catMap.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, value]) => ({ label, value: Math.round(value), amount: nairaFmt(Math.round(value)) }))

  // All-time totals
  const totalCredit  = Math.round(allTx.filter(t => t.type === 'credit').reduce((s, t) => s + koboToNaira(t.amount), 0))
  const totalDebit   = Math.round(allTx.filter(t => t.type === 'debit').reduce((s, t) => s + koboToNaira(t.amount), 0))

  return {
    banks,
    monthlyRows,
    mtd,
    chartData,
    spendByCategory,
    totalCredit,
    totalDebit,
    loading,
    error,
    reload: load,
  }
}
