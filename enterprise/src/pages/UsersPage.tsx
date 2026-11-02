import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import StatCard from '@/components/StatCard'
import SegmentedTabs from '@/components/SegmentedTabs'
import RemixIcon from '@/components/RemixIcon'
import { Button, PageHeader, Panel, Pill, SearchInput, Table } from '@/components/ui'
import type { Tone } from '@/data/mock'
import { useMode } from '@/contexts/ModeContext'
import { shortDate, useFetch } from '@/lib/useFetch'
import { download } from '@/lib/download'
import { apiErrorMessage } from '@/lib/api'

const PAGE_SIZE = 25
type Status = 'verified' | 'pending' | 'declined' | 'revoked'
type Filter = 'all' | Status
interface ConsoleUser {
  id: string; code: string; customer_ref: string | null; name: string | null; email: string | null
  checks: string[]; status: Status; has_foid_account: boolean; verified_at: string | null; created_at: string
}
interface UsersResponse { data: ConsoleUser[]; total: number; counts: Record<Filter, number> }
interface SubjectDetail {
  consent: { status: string; scopes: string[] }
  first_name?: string; last_name?: string; date_of_birth?: string; email?: string; phone?: string
  nin?: { verified: boolean; last4: string | null }; bvn?: { verified: boolean; last4: string | null }
  checks: { id: string; type: string; status: string; reasons?: string[]; redacted?: boolean; created_at: string }[]
}

const TABS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' }, { key: 'verified', label: 'Verified' }, { key: 'pending', label: 'Pending' },
  { key: 'declined', label: 'Declined' }, { key: 'revoked', label: 'Revoked' },
]
const TONE: Record<string, Tone> = { verified: 'success', passed: 'success', pending: 'warning', needs_review: 'warning',
  declined: 'failed', failed: 'failed', error: 'failed', revoked: 'neutral' }
const cap = (s: string) => s[0].toUpperCase() + s.slice(1).replace('_', ' ')

function Detail({ base, user, onClose }: { base: string; user: ConsoleUser; onClose: () => void }) {
  const { data, error } = useFetch<SubjectDetail>(`${base}/subjects/${user.id}`)
  const rows: [string, string | null | undefined][] = data ? [
    ['Name', [data.first_name, data.last_name].filter(Boolean).join(' ') || null],
    ['Date of birth', data.date_of_birth], ['Email', data.email], ['Phone', data.phone],
    ['NIN', data.nin?.last4 ? `•••• ${data.nin.last4}${data.nin.verified ? ' · verified' : ''}` : null],
    ['BVN', data.bvn?.last4 ? `•••• ${data.bvn.last4}${data.bvn.verified ? ' · verified' : ''}` : null],
  ] : []
  return (
    <div className="fixed inset-0 z-[90] flex justify-end bg-black/30" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="w-full sm:w-[440px] h-full bg-white shadow-2xl overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100">
          <div>
            <div className="text-[17px] font-bold">{user.name ?? 'Hidden by consent'}</div>
            <div className="text-[12px] font-mono text-neutral-500">{user.code}{user.customer_ref ? ` · ${user.customer_ref}` : ''}</div>
          </div>
          <button onClick={onClose} aria-label="Close" className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-neutral-100">
            <RemixIcon name="ri-close-line" size={20} color="#71717a" />
          </button>
        </div>
        <div className="p-6 flex flex-col gap-5 text-[13.5px]">
          <div className="flex flex-wrap gap-2">
            <Pill tone={TONE[user.status]} dot>{cap(user.status)}</Pill>
            {user.has_foid_account && <Pill tone="brand">Has a FOID account</Pill>}
          </div>
          {error && <p className="text-red-500">{error}</p>}
          {data && (
            <>
              <section>
                <h3 className="text-[12px] font-bold text-neutral-500 uppercase tracking-wider mb-2">Consent</h3>
                <p>{data.consent.status === 'active' ? `Active — ${data.consent.scopes.join(', ')}` :
                    data.consent.status === 'revoked' ? 'Revoked by the person. Their data is hidden and no more updates are sent.' : 'Not given yet'}</p>
              </section>
              <section>
                <h3 className="text-[12px] font-bold text-neutral-500 uppercase tracking-wider mb-2">Details</h3>
                <dl className="grid grid-cols-[110px_1fr] gap-y-1.5">
                  {rows.flatMap(([k, v]) => [<dt key={k} className="text-neutral-500">{k}</dt>,
                    <dd key={`${k}-v`}>{v || <span className="text-neutral-400">—</span>}</dd>])}
                </dl>
              </section>
              <section>
                <h3 className="text-[12px] font-bold text-neutral-500 uppercase tracking-wider mb-2">Checks</h3>
                {data.checks.length === 0 && <p className="text-neutral-400">No checks yet</p>}
                <ul className="flex flex-col gap-2">
                  {data.checks.map(c => (
                    <li key={c.id} className="flex items-center justify-between gap-2 rounded-xl border border-neutral-200 px-3 py-2">
                      <span className="font-semibold uppercase text-[12px]">{c.type}</span>
                      <span className="text-[12px] text-neutral-500 truncate">{c.redacted ? 'details hidden' : (c.reasons ?? []).join(', ')}</span>
                      <span className="flex items-center gap-2"><Pill tone={TONE[c.status] ?? 'neutral'}>{cap(c.status)}</Pill>
                        <span className="text-[11px] text-neutral-400 whitespace-nowrap">{shortDate(c.created_at)}</span></span>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}

export default function UsersPage() {
  const { org, mode, can } = useMode()
  const [params] = useSearchParams()
  const [exportErr, setExportErr] = useState('')
  const [filter, setFilter] = useState<Filter>((params.get('status') as Filter) || 'all')
  const [query, setQuery] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState<ConsoleUser | null>(null)
  useEffect(() => { const q0 = params.get('q'); if (q0) setQuery(q0) }, [params])

  useEffect(() => { const t = setTimeout(() => { setQ(query.trim()); setPage(0) }, 300); return () => clearTimeout(t) }, [query])

  const base = org ? `/business/organisations/${org.id}` : null
  const search = new URLSearchParams({ env: mode, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE),
    ...(filter !== 'all' && { status: filter }), ...(q && { q }) })
  const { data, error, loading } = useFetch<UsersResponse>(base && `${base}/users?${search}`)
  const c = data?.counts
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="pb-8">
      <PageHeader title="Users" subtitle="Everyone who has verified their identity through your integration">
        {can('reviewer') && <Button variant="outline" icon="ri-download-2-line" onClick={() => {
          setExportErr('')
          const f = new URLSearchParams({ env: mode, ...(filter !== 'all' && { status: filter }), ...(q && { q }) })
          download(`${base}/users/export?${f}`).catch(e => setExportErr(apiErrorMessage(e, 'Export failed')))
        }}>Export Report</Button>}
      </PageHeader>
      {exportErr && <p className="mb-4 text-[13px] text-red-500">{exportErr}</p>}

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-5 mb-6">
        <StatCard label="Registered users" value={c ? c.all.toLocaleString() : '—'} sub={mode === 'test' ? 'Sandbox only' : 'All time'} icon="ri-group-line" />
        <StatCard label="Verified" value={c ? c.verified.toLocaleString() : '—'} sub="Passed the checks you asked for" subColor="text-green-600" icon="ri-shield-check-line" />
        <StatCard label="Pending" value={c ? c.pending.toLocaleString() : '—'} sub="Started, not finished" subColor="text-orange-700" icon="ri-time-line" />
        <StatCard label="Declined / revoked" value={c ? (c.declined + c.revoked).toLocaleString() : '—'} sub="Failed a check or withdrew consent" subColor="text-red-500" icon="ri-close-circle-line" />
      </div>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div className="w-max max-w-full overflow-x-auto"><SegmentedTabs tabs={TABS} value={filter} onChange={f => { setFilter(f); setPage(0) }} /></div>
        <SearchInput value={query} onChange={setQuery} placeholder="Search name, email, FOID code or your ref" />
      </div>

      <Panel>
        <Table cols={['User', 'FOID code', 'Checks', 'Status', 'Verified on']}>
          {data?.data.map(u => (
            <tr key={u.id} onClick={() => setOpen(u)} className="cursor-pointer hover:bg-neutral-50">
              <td>
                <div className="font-semibold text-neutral-900">{u.name ?? <span className="text-neutral-400 font-normal">Hidden by consent</span>}</div>
                <div className="text-[12px] text-neutral-500">{u.email ?? u.customer_ref ?? '—'}</div>
              </td>
              <td className="font-mono text-[13px] whitespace-nowrap">{u.code}</td>
              <td><div className="flex flex-wrap gap-1">{u.checks.length ? u.checks.map(ch => <Pill key={ch} tone="neutral">{ch}</Pill>) : <span className="text-neutral-400">—</span>}</div></td>
              <td><Pill tone={TONE[u.status]} dot>{cap(u.status)}</Pill></td>
              <td className="whitespace-nowrap">{shortDate(u.verified_at)}</td>
            </tr>
          ))}
          {data && !data.data.length && (
            <tr><td colSpan={5} className="text-center !text-neutral-400 !py-10">
              {q || filter !== 'all' ? 'No users match' : `No ${mode} users yet — they appear here when you run a verification with a ${mode} key`}
            </td></tr>
          )}
          {error && <tr><td colSpan={5} className="text-center !text-red-500 !py-10">{error}</td></tr>}
        </Table>
        <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-200 text-[13px] text-neutral-500">
          <span>{loading ? 'Loading…' : total ? `${page * PAGE_SIZE + 1}–${Math.min(total, (page + 1) * PAGE_SIZE)} of ${total}` : '0 results'}</span>
          <div className="flex gap-2">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
              className="px-4 py-1.5 rounded-full border border-neutral-200 font-semibold disabled:opacity-40">Previous</button>
            <button disabled={page >= pages - 1} onClick={() => setPage(p => p + 1)}
              className="px-4 py-1.5 rounded-full border border-neutral-200 font-semibold disabled:opacity-40">Next</button>
          </div>
        </div>
      </Panel>

      {open && base && <Detail base={base} user={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
