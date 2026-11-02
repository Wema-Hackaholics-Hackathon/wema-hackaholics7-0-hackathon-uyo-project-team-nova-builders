import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Modal, { Confirm, inputCls } from '@/components/Modal'
import { useAuth } from '@/contexts/AuthContext'
import { useFetch } from '@/lib/useFetch'
import SegmentedTabs from '@/components/SegmentedTabs'
import { Button, Field, PageHeader, Panel } from '@/components/ui'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'

const pillInput = 'px-4 py-2.5 rounded-full border border-neutral-300 text-[13.5px] text-neutral-700 focus:outline-none focus:border-brand-400 disabled:bg-neutral-50'

/** Company name + support email are saved; the CBN licence number is a placeholder for now. */
function OrgProfile() {
  const { org, can, reloadOrgs } = useMode()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setName(org?.name ?? ''); setEmail(org?.support_email ?? '') }, [org])
  const canEdit = can('admin')

  const save = async () => {
    setBusy(true); setMsg(null)
    try {
      await api.patch(`/business/organisations/${org!.id}`, { name: name.trim(), support_email: email.trim() || null })
      await reloadOrgs()
      setMsg({ ok: true, text: 'Saved' })
    } catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) } finally { setBusy(false) }
  }

  return (
    <Panel title="Organization profile">
      <div className="p-6 flex flex-col gap-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <label className="flex flex-col gap-2">
            <span className="text-[15px] font-semibold text-neutral-900">Company name</span>
            <input className={pillInput} value={name} disabled={!canEdit} onChange={e => setName(e.target.value)} maxLength={120} />
          </label>
          <Field label="CBN licence number" defaultValue="MFB/2019/00214" />
          <label className="flex flex-col gap-2">
            <span className="text-[15px] font-semibold text-neutral-900">Support email</span>
            <input className={pillInput} type="email" value={email} disabled={!canEdit} placeholder="support@company.com" onChange={e => setEmail(e.target.value)} />
          </label>
        </div>
        {canEdit ? (
          <div className="flex items-center gap-3">
            <span className={busy || name.trim().length < 2 ? 'opacity-50 pointer-events-none' : ''}>
              <Button onClick={() => void save()}>{busy ? 'Saving…' : 'Save changes'}</Button>
            </span>
            {msg && <span className={`text-[13px] ${msg.ok ? 'text-green-600' : 'text-red-500'}`}>{msg.text}</span>}
          </div>
        ) : <p className="text-[12.5px] text-neutral-500">Only owners and admins can change these.</p>}
      </div>
    </Panel>
  )
}

type Tab = 'org' | 'security' | 'danger'
const TABS: { key: Tab; label: string }[] = [{ key: 'org', label: 'Organization' }, { key: 'security', label: 'Security' }, { key: 'danger', label: 'Danger Zone' }]

interface Sec { require_2fa: boolean; alert_on_key_create: boolean; ip_allowlist: string[] }

function SecuritySettings() {
  const { org, can, reloadOrgs } = useMode()
  const { member } = useAuth()
  const { data } = useFetch<Sec>(org ? `/business/organisations/${org.id}/security` : null)
  const [sec, setSec] = useState<Sec | null>(null)
  const [restrict, setRestrict] = useState(false)
  const [ips, setIps] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => { if (data) { setSec(data); setRestrict(data.ip_allowlist.length > 0); setIps(data.ip_allowlist.join(', ')) } }, [data])
  if (!sec) return null
  const canEdit = can('admin')

  const save = async () => {
    setMsg(null)
    const list = restrict ? ips.split(/[\s,]+/).filter(Boolean) : []
    if (restrict && !list.length) { setMsg({ ok: false, text: 'Add at least one IP address, or untick the restriction' }); return }
    try {
      setSec((await api.put<Sec>(`/business/organisations/${org!.id}/security`, { ...sec, ip_allowlist: list })).data)
      await reloadOrgs()
      setMsg({ ok: true, text: 'Saved' })
    } catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }
  const box = (label: string, checked: boolean, onChange: (v: boolean) => void, hint?: React.ReactNode) => (
    <label className="flex items-start gap-3 text-[13.5px] font-medium cursor-pointer">
      <input type="checkbox" checked={checked} disabled={!canEdit} onChange={e => onChange(e.target.checked)} className="mt-0.5 w-4 h-4 accent-[#C800DE]" />
      <span>{label}{hint && <span className="block text-[12px] font-normal text-neutral-500">{hint}</span>}</span>
    </label>
  )
  return (
    <Panel title="Security">
      <div className="p-6 flex flex-col gap-4">
        {box('Require two-step sign-in for all team members', sec.require_2fa, v => setSec({ ...sec, require_2fa: v }),
          member?.two_factor_enabled ? 'Members without it can’t open this business until they turn it on in My account.'
            : <>Turn it on for yourself first in <Link to="/account" className="text-[#C800DE] font-semibold">My account</Link>.</>)}
        {box('Email alert on new API key creation', sec.alert_on_key_create, v => setSec({ ...sec, alert_on_key_create: v }), 'Sent to owners and admins.')}
        {box('Restrict live API keys to allow-listed IP addresses', restrict, setRestrict, 'Test keys keep working from anywhere.')}
        {restrict && (
          <label className="flex flex-col gap-2 mt-1">
            <span className="text-[15px] font-semibold text-neutral-900">Allow-listed IPs</span>
            <input value={ips} disabled={!canEdit} onChange={e => setIps(e.target.value)} placeholder="102.84.29.18, 102.84.29.0/24"
              className="px-4 py-2.5 rounded-full border border-neutral-300 text-[13.5px] text-neutral-700 focus:outline-none focus:border-brand-400" />
          </label>
        )}
        {canEdit ? <div className="flex items-center gap-3"><Button onClick={() => void save()}>Save changes</Button>
          {msg && <span className={`text-[13px] ${msg.ok ? 'text-green-600' : 'text-red-500'}`}>{msg.text}</span>}</div>
          : <p className="text-[12.5px] text-neutral-500">Only owners and admins can change these.</p>}
      </div>
    </Panel>
  )
}

function DangerZone() {
  const { org, reloadOrgs } = useMode()
  const [dialog, setDialog] = useState<'keys' | 'deactivate' | null>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const base = `/business/organisations/${org!.id}`
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr('')
    try { await fn(); setDialog(null) } catch (e) { setErr(apiErrorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Panel title="Danger zone">
      <div className="px-6 divide-y divide-neutral-200">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-5">
          <div>
            <div className="text-[15px] font-semibold">Revoke all API keys</div>
            <div className="text-[12.5px] text-neutral-600">Immediately disables every live and test key on this business.</div>
          </div>
          <Button variant="danger" onClick={() => { setErr(''); setDialog('keys') }}>Revoke all keys</Button>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-5">
          <div>
            <div className="text-[15px] font-semibold">Deactivate organization</div>
            <div className="text-[12.5px] text-neutral-600">Suspends this console and all API access. Your data is kept for 30 days, then deleted.</div>
          </div>
          <Button variant="danger" onClick={() => { setErr(''); setTyped(''); setDialog('deactivate') }}>Deactivate</Button>
        </div>
        {msg && <p className="py-3 text-[13px] text-green-600">{msg}</p>}
      </div>
      {dialog === 'keys' && (
        <Modal title="Revoke all API keys" onClose={() => setDialog(null)}>
          <Confirm danger text="Every live and test key for this business stops working now. Your integrations will fail until you create new keys."
            action="Revoke all keys" busy={busy} error={err} onCancel={() => setDialog(null)}
            onConfirm={() => void run(async () => { const r = (await api.post<{ revoked: number }>(`${base}/api-keys/revoke-all`)).data; setMsg(`${r.revoked} key${r.revoked === 1 ? '' : 's'} revoked`) })} />
        </Modal>
      )}
      {dialog === 'deactivate' && (
        <Modal title="Deactivate organization" onClose={() => setDialog(null)}>
          <p className="text-[14px] text-neutral-600">API access stops, webhooks stop, and the team can’t use this business. You can reactivate within 30 days; after that everything is deleted.</p>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Type <b>{org!.name}</b> to confirm
            <input className={inputCls} value={typed} onChange={e => setTyped(e.target.value)} autoFocus /></label>
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={typed !== org!.name || busy ? 'opacity-50 pointer-events-none' : ''}>
            <Button variant="danger" onClick={() => void run(async () => { await api.post(`${base}/deactivate`, { confirm_name: typed }); await reloadOrgs() })}>Deactivate</Button>
          </span>
        </Modal>
      )}
    </Panel>
  )
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('org')
  const { can } = useMode()
  const tabs = can('owner') ? TABS : TABS.filter(t => t.key !== 'danger')   // danger zone: owner only
  return (
    <div className="pb-8">
      <PageHeader title="Settings" subtitle="Organization profile, security, and API configuration" />
      <div className="mb-6 w-max max-w-full overflow-x-auto"><SegmentedTabs tabs={tabs} value={tab} onChange={setTab} /></div>

      {tab === 'org' && <OrgProfile />}

      {tab === 'security' && <SecuritySettings />}
      {tab === 'danger' && <DangerZone />}
    </div>
  )
}
