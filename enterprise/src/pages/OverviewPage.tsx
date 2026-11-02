import { Link, useNavigate } from 'react-router-dom'
import StatCard from '@/components/StatCard'
import IncomeExpenseChart from '@/components/IncomeExpenseChart'
import RemixIcon from '@/components/RemixIcon'
import { Button, PageHeader, Panel, Pill, Table } from '@/components/ui'
import { useMode } from '@/contexts/ModeContext'
import { useAuth } from '@/contexts/AuthContext'
import type { Tone } from '@/data/mock'
import { download } from '@/lib/download'
import { ago, useFetch } from '@/lib/useFetch'

interface Overview {
  users: Record<'all' | 'verified' | 'pending' | 'declined' | 'revoked', number>
  verifications_30d: number; verifications_prev_30d: number; pass_rate: number | null
  avg_verification_seconds: number | null; stuck: number; foid_account_share: number | null
  funnel: { started: number; identity_confirmed: number; fully_verified: number }
}
interface Stats { total: number; previous_total: number; series: { day: string; successful: number; failed: number }[] }
interface Activity { kind: string; title: string; actor: string; status: 'success' | 'failed' | 'pending' | 'team'; at: string | null }

const ACT_ICON: Record<string, string> = { verification: 'ri-shield-check-line', webhook: 'ri-webhook-line', team: 'ri-team-line' }
const ACT_TONE: Record<Activity['status'], [Tone, string]> = {
  success: ['success', 'Success'], failed: ['failed', 'Failed'], pending: ['warning', 'Pending'], team: ['brand', 'Team action'],
}
const day = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

const pct = (n: number | null) => n == null ? '—' : `${Math.round(n * 1000) / 10}%`
const secs = (n: number | null) => n == null ? '—' : n < 90 ? `${n}s` : `${Math.round(n / 60)}m`
function trend(now: number, prev: number) {
  if (!prev) return now ? 'New this month' : 'Nothing yet this month'
  const ch = ((now - prev) / prev) * 100
  return `${ch >= 0 ? '↑' : '↓'} ${Math.abs(ch).toFixed(1)}% vs last month`
}

export default function OverviewPage() {
  const { org, mode, can } = useMode()
  const { member } = useAuth()
  const navigate = useNavigate()
  const base = org ? `/business/organisations/${org.id}` : null
  const { data: o } = useFetch<Overview>(base && `${base}/overview?env=${mode}`)
  const { data: st } = useFetch<Stats>(base && `${base}/request-stats?env=${mode}&days=30`)
  const { data: feed } = useFetch<Activity[]>(base && `${base}/activity?env=${mode}&limit=8`)
  const chart = st?.series.map(p => ({ week: day(p.day), income: p.successful, expense: p.failed })) ?? []
  const stats = [
    { label: 'Verified users', value: o ? o.users.verified.toLocaleString() : '—', icon: 'ri-bank-line', subColor: 'text-brand-500',
      sub: o?.foid_account_share != null ? `${pct(o.foid_account_share)} already had a FOID account` : 'Across all your checks' },
    { label: 'API requests (30d)', value: st ? st.total.toLocaleString() : '—', icon: 'ri-shield-user-line', subColor: 'text-green-600',
      sub: st ? trend(st.total, st.previous_total) : '' },
    { label: 'Verification success rate', value: pct(o?.pass_rate ?? null), icon: 'ri-layout-right-2-line', subColor: 'text-green-600',
      sub: 'Of finished verifications, 30d' },
    { label: 'Avg. verification time', value: secs(o?.avg_verification_seconds ?? null), icon: 'ri-quill-pen-line',
      sub: 'Start to pass, 30d' },
  ]
  const f = o?.funnel
  const funnel = f ? [
    { label: 'Started', count: f.started, color: '#C800DE' },
    { label: 'Identity confirmed', count: f.identity_confirmed, color: '#C800DE' },
    { label: 'Fully verified', count: f.fully_verified, color: '#16a34a' },
  ] : []
  return (
    <div className="pb-8">
      <PageHeader title={`Welcome back, ${member?.first_name ?? ''}`}
        subtitle={`How your users and integration are performing on FOID — ${mode} environment`}>
        {can('reviewer') && <Button variant="outline" icon="ri-download-2-line" onClick={() => void download(`${base}/users/export?env=${mode}`)}>Export Report</Button>}
        {can('developer') && <Button icon="ri-add-line" onClick={() => navigate('/api-keys')}>Create API key</Button>}
      </PageHeader>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-5 mb-6">
        {stats.map(s => <StatCard key={s.label} {...s} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-6 mb-6">
        <IncomeExpenseChart data={chart} height={300} money={false} names={['Successful', 'Failed']}
          title="API requests" subtitle={`Last 30 days · ${mode} environment`} />

        <Panel title="Verification funnel">
          <div className="p-6 flex flex-col gap-5">
            {funnel.map(f => (
              <div key={f.label}>
                <div className="flex justify-between text-[14px] mb-2">
                  <span className="font-medium text-neutral-900">{f.label}</span>
                  <span className="text-[12px] font-semibold text-neutral-700">{f.count.toLocaleString()}</span>
                </div>
                <div className="h-1.5 rounded-full bg-neutral-100">
                  <div className="h-full rounded-full" style={{ width: `${funnel[0].count ? (f.count / funnel[0].count) * 100 : 0}%`, background: f.color }} />
                </div>
              </div>
            ))}
            {o && (
              <div className="rounded-xl bg-neutral-100 p-4 flex flex-col gap-3">
                <p className="flex gap-2 text-[12.5px] text-neutral-600">
                  <RemixIcon name="ri-information-line" size={18} color="#C800DE" />
                  {o.stuck ? `${o.stuck} ${o.stuck === 1 ? 'person has' : 'people have'} been stuck for over 30 minutes.`
                    : o.users.pending ? `${o.users.pending} pending — none stuck right now.` : 'Nobody is stuck right now.'}
                </p>
                {o.users.pending > 0 && (
                  <Link to="/users?status=pending" className="text-center py-2 rounded-full text-white text-[13px] font-semibold" style={{ background: '#C800DE' }}>
                    Review these users
                  </Link>
                )}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Recent activity" subtitle="Verifications, webhook deliveries, and team actions"
        action={<Link to="/logs" className="px-3 py-1.5 rounded-full border border-neutral-200 text-[12.5px] font-semibold">View all logs</Link>}>
        <Table cols={['Event', 'User / Actor', 'Status', 'Time']}>
          {feed?.map((a, i) => (
            <tr key={i}>
              <td><span className="flex items-center gap-2"><RemixIcon name={ACT_ICON[a.kind] ?? 'ri-information-line'} size={17} color="#3f3f46" />{a.title}</span></td>
              <td className="font-mono text-[13px]">{a.actor}</td>
              <td><Pill tone={ACT_TONE[a.status][0]} dot={a.status !== 'team'}>{ACT_TONE[a.status][1]}</Pill></td>
              <td className="whitespace-nowrap">{ago(a.at)}</td>
            </tr>
          ))}
          {feed && !feed.length && <tr><td colSpan={4} className="text-center !text-neutral-400 !py-10">Nothing has happened in {mode} yet</td></tr>}
        </Table>
      </Panel>
    </div>
  )
}
