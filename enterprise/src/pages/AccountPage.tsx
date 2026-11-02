/**
 * My account — the person, not the business: name, password, two-step sign-in, and the
 * businesses they belong to (plus "Create another business").
 */
import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import RemixIcon from '@/components/RemixIcon'
import Modal, { inputCls } from '@/components/Modal'
import { Button, PageHeader, Panel, Pill } from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage, setTokens } from '@/lib/api'
import { PasswordRules, PWD_RULES } from '@/components/AuthShell'

const pill = 'px-4 py-2.5 rounded-full border border-neutral-300 text-[13.5px] focus:outline-none focus:border-brand-400 w-full'
type Msg = { ok: boolean; text: string } | null
const Note = ({ m }: { m: Msg }) => m ? <span className={`text-[13px] ${m.ok ? 'text-green-600' : 'text-red-500'}`}>{m.text}</span> : null

function Profile() {
  const { member, refreshMember } = useAuth()
  const [first, setFirst] = useState(member?.first_name ?? '')
  const [last, setLast] = useState(member?.last_name ?? '')
  const [msg, setMsg] = useState<Msg>(null)
  const save = async () => {
    setMsg(null)
    try { await api.patch('/console/auth/me', { first_name: first.trim(), last_name: last.trim() }); await refreshMember(); setMsg({ ok: true, text: 'Saved' }) }
    catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }
  return (
    <Panel title="Profile" subtitle="Your console account — separate from any personal FOID account">
      <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-5">
        <label className="flex flex-col gap-2 text-[15px] font-semibold">First name<input className={pill} value={first} onChange={e => setFirst(e.target.value)} /></label>
        <label className="flex flex-col gap-2 text-[15px] font-semibold">Last name<input className={pill} value={last} onChange={e => setLast(e.target.value)} /></label>
        <label className="flex flex-col gap-2 text-[15px] font-semibold">Email<input className={`${pill} bg-neutral-50 text-neutral-500`} value={member?.email ?? ''} disabled /></label>
        <div className="flex items-center gap-3"><Button onClick={() => void save()}>Save changes</Button><Note m={msg} /></div>
      </div>
    </Panel>
  )
}

function Password() {
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  const save = async () => {
    setMsg(null)
    try {
      const t = (await api.post<{ access_token: string; refresh_token: string }>('/console/auth/me/password', { current_password: cur, new_password: next })).data
      setTokens(t.access_token, t.refresh_token)
      setCur(''); setNext(''); setMsg({ ok: true, text: 'Password changed — other devices were signed out' })
    } catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }
  return (
    <Panel title="Password">
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
        <label className="flex flex-col gap-2 text-[15px] font-semibold">Current password<input type="password" className={pill} value={cur} onChange={e => setCur(e.target.value)} autoComplete="current-password" /></label>
        <label className="flex flex-col gap-2 text-[15px] font-semibold">New password<input type="password" className={pill} value={next} onChange={e => setNext(e.target.value)} autoComplete="new-password" /></label>
        {next && <div className="md:col-span-2"><PasswordRules password={next} /></div>}
        <div className="flex items-center gap-3">
          <span className={!cur || !PWD_RULES.every(r => r.test(next)) ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void save()}>Change password</Button></span>
          <Note m={msg} />
        </div>
      </div>
    </Panel>
  )
}

function TwoFactor() {
  const { member, refreshMember } = useAuth()
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null)
  const [disabling, setDisabling] = useState(false)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  const on = member?.two_factor_enabled

  const start = async () => {
    setMsg(null); setCode('')
    try {
      const r = (await api.post<{ secret: string; otpauth_uri: string }>('/console/auth/me/2fa/setup')).data
      setSetup({ secret: r.secret, qr: await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 200 }) })
    } catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }
  const enable = async () => {
    try { await api.post('/console/auth/me/2fa/enable', { code }); await refreshMember(); setSetup(null); setMsg({ ok: true, text: 'Two-step sign-in is on' }) }
    catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }
  const disable = async () => {
    try { await api.post('/console/auth/me/2fa/disable', { password, code }); await refreshMember(); setDisabling(false); setMsg({ ok: true, text: 'Two-step sign-in is off' }) }
    catch (e) { setMsg({ ok: false, text: apiErrorMessage(e) }) }
  }

  return (
    <Panel title="Two-step sign-in" subtitle="After your password, enter a code from an authenticator app (Google Authenticator, 1Password, Authy…)">
      <div className="p-6 flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {on ? <Pill tone="success" dot>On</Pill> : <Pill tone="neutral">Off</Pill>}
          {on ? <Button variant="outline" onClick={() => { setMsg(null); setCode(''); setPassword(''); setDisabling(true) }}>Turn off</Button>
            : !setup && <Button icon="ri-shield-keyhole-line" onClick={() => void start()}>Set up</Button>}
          <Note m={msg} />
        </div>
        {setup && (
          <div className="flex flex-col sm:flex-row gap-5 items-start rounded-xl border border-neutral-200 p-4">
            <img src={setup.qr} alt="QR code for your authenticator app" width={180} height={180} className="rounded-lg border border-neutral-200" />
            <div className="flex-1 flex flex-col gap-3 text-[13px]">
              <p>1. Scan the QR code with your authenticator app. Can’t scan? Enter this key: <code className="font-mono bg-neutral-100 rounded px-1 break-all">{setup.secret}</code></p>
              <p>2. Enter the 6-digit code it shows:</p>
              <input className={inputCls} inputMode="numeric" maxLength={6} placeholder="123456" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
              <div className="flex gap-2">
                <span className={code.length !== 6 ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void enable()}>Turn on</Button></span>
                <Button variant="outline" onClick={() => setSetup(null)}>Cancel</Button>
              </div>
            </div>
          </div>
        )}
      </div>
      {disabling && (
        <Modal title="Turn off two-step sign-in" onClose={() => setDisabling(false)}>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Password<input type="password" className={inputCls} value={password} onChange={e => setPassword(e.target.value)} /></label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Authenticator code
            <input className={inputCls} inputMode="numeric" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} /></label>
          {msg && !msg.ok && <p className="text-[13px] text-red-500">{msg.text}</p>}
          <span className={!password || code.length !== 6 ? 'opacity-50 pointer-events-none' : ''}><Button variant="danger" onClick={() => void disable()}>Turn off</Button></span>
        </Modal>
      )}
    </Panel>
  )
}

export function CreateBusiness({ onClose }: { onClose: () => void }) {
  const { reloadOrgs, selectOrg } = useMode()
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const create = async () => {
    setErr('')
    try {
      const org = (await api.post<{ id: string }>('/business/organisations', { name: name.trim() })).data
      await reloadOrgs(); selectOrg(org.id); onClose()
    } catch (e) { setErr(apiErrorMessage(e)) }
  }
  return (
    <Modal title="Create another business" onClose={onClose}>
      <p className="text-[12.5px] text-neutral-500">Each business has its own go-live documents, API keys, users, team and billing. Nothing is shared between them.</p>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Business name
        <input className={inputCls} value={name} onChange={e => setName(e.target.value)} maxLength={120} autoFocus /></label>
      {err && <p className="text-[13px] text-red-500">{err}</p>}
      <span className={name.trim().length < 2 ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void create()}>Create business</Button></span>
    </Modal>
  )
}

function Businesses() {
  const { orgs, org, selectOrg } = useMode()
  const [creating, setCreating] = useState(false)
  return (
    <Panel title="Your businesses" action={<button onClick={() => setCreating(true)} className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-neutral-200 text-[12.5px] font-semibold">
      <RemixIcon name="ri-add-line" size={14} /> Create another business</button>}>
      {orgs.map(o => (
        <div key={o.id} className="flex items-center gap-3 px-6 py-4 border-b border-neutral-200 last:border-0">
          <span className="w-9 h-9 rounded-lg bg-brand-100 flex items-center justify-center font-bold text-brand-600">{o.name[0]?.toUpperCase()}</span>
          <div className="flex-1 min-w-0">
            <div className="font-semibold truncate">{o.name}</div>
            <div className="text-[12px] text-neutral-500 capitalize">{o.role} · {o.plan} plan · {o.kyb_status === 'approved' ? 'Live enabled' : 'Test only'}{o.status !== 'active' ? ' · deactivated' : ''}</div>
          </div>
          {o.id === org?.id ? <Pill tone="brand">Current</Pill> : <button onClick={() => selectOrg(o.id)} className="px-4 py-1.5 rounded-full border border-neutral-200 text-[13px] font-semibold">Switch</button>}
        </div>
      ))}
      {creating && <CreateBusiness onClose={() => setCreating(false)} />}
    </Panel>
  )
}

export default function AccountPage() {
  const { refreshMember } = useAuth()
  useEffect(() => { void refreshMember() }, [refreshMember])
  return (
    <div className="pb-8 flex flex-col gap-6">
      <PageHeader title="My account" subtitle="Your sign-in details and the businesses you belong to" />
      <Profile />
      <Password />
      <TwoFactor />
      <Businesses />
    </div>
  )
}
