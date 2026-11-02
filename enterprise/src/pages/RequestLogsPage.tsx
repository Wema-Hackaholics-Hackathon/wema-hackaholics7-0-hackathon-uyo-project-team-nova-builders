import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import SegmentedTabs from '@/components/SegmentedTabs'
import { Button, PageHeader, Panel, Pill, SearchInput, Table } from '@/components/ui'
import type { Tone } from '@/data/mock'
import { useMode } from '@/contexts/ModeContext'
import { apiErrorMessage } from '@/lib/api'
import { download } from '@/lib/download'
import { ago, useFetch } from '@/lib/useFetch'

const PAGE_SIZE = 25
type Filter = 'all' | '2' | '4' | '5'
interface Log { request_id: string; method: string; path: string; status: number; latency_ms: number; key_hint: string | null; created_at: string }
const TABS: { key: Filter; label: string }[] = [{ key: 'all', label: 'All' }, { key: '2', label: '2XX' }, { key: '4', label: '4XX' }, { key: '5', label: '5XX' }]
const tone = (s: number): Tone => s < 300 ? 'success' : s < 500 ? 'warning' : 'failed'
const keyTail = (hint: string | null) => hint ? `••${hint.slice(-2)}` : '—'

export default function RequestLogsPage() {
  const { org, mode } = useMode()
  const [params] = useSearchParams()
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [q, setQ] = useState(query)
  const [page, setPage] = useState(0)
  const [err, setErr] = useState('')
  useEffect(() => { const t = setTimeout(() => { setQ(query.trim()); setPage(0) }, 300); return () => clearTimeout(t) }, [query])
  useEffect(() => {   // top-bar search links here with ?q=req_…
    const q0 = params.get('q')
    if (q0) { setQuery(q0); setFilter('all') }
  }, [params])

  const base = org ? `/business/organisations/${org.id}/request-logs` : null
  const filters = new URLSearchParams({ env: mode, ...(filter !== 'all' && { status_class: filter }), ...(q && { q }) })
  const { data, error, loading } = useFetch<{ data: Log[]; total: number }>(
    base && `${base}?${filters}&limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`)
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const exportCsv = async () => {
    setErr('')
    try { await download(`${base}/export?${filters}`) } catch (e) { setErr(apiErrorMessage(e, 'Export failed')) }
  }

  return (
    <div className="pb-8">
      <PageHeader title="Request logs" subtitle={`Every API call made with your ${mode} keys — kept for 30 days`}>
        <Button variant="outline" icon="ri-download-2-line" onClick={() => void exportCsv()}>Export</Button>
      </PageHeader>
      {err && <p className="mb-4 text-[13px] text-red-500">{err}</p>}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <SegmentedTabs tabs={TABS} value={filter} onChange={f => { setFilter(f); setPage(0) }} />
        <SearchInput value={query} onChange={setQuery} placeholder="Filter by endpoint or request ID" />
      </div>

      <Panel>
        <Table cols={['Status', 'Method', 'Endpoint', 'Key', 'Latency', 'Time']}>
          {data?.data.map(r => (
            <tr key={r.request_id} className="hover:bg-neutral-50" title={r.request_id}>
              <td><Pill tone={tone(r.status)}>{r.status}</Pill></td>
              <td className="font-semibold">{r.method}</td>
              <td className="font-mono text-[13px]">
                <div>{r.path}</div>
                <div className="text-[11px] text-neutral-400">{r.request_id}</div>
              </td>
              <td className="font-mono text-[13px]" title={r.key_hint ?? ''}>{keyTail(r.key_hint)}</td>
              <td>{r.latency_ms}ms</td>
              <td className="whitespace-nowrap">{ago(r.created_at)}</td>
            </tr>
          ))}
          {data && !data.data.length && (
            <tr><td colSpan={6} className="text-center !text-neutral-400 !py-10">
              {q || filter !== 'all' ? 'No requests match' : `No ${mode} API calls yet — they show up here as soon as you call the API with a ${mode} key`}
            </td></tr>
          )}
          {error && <tr><td colSpan={6} className="text-center !text-red-500 !py-10">{error}</td></tr>}
        </Table>
        <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-200 text-[13px] text-neutral-500">
          <span>{loading ? 'Loading…' : total ? `${page * PAGE_SIZE + 1}–${Math.min(total, (page + 1) * PAGE_SIZE)} of ${total}` : '0 results'}</span>
          <div className="flex gap-2">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-4 py-1.5 rounded-full border border-neutral-200 font-semibold disabled:opacity-40">Previous</button>
            <button disabled={page >= pages - 1} onClick={() => setPage(p => p + 1)} className="px-4 py-1.5 rounded-full border border-neutral-200 font-semibold disabled:opacity-40">Next</button>
          </div>
        </div>
      </Panel>
    </div>
  )
}
