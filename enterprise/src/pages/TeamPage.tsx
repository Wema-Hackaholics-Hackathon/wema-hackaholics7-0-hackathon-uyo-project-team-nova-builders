import { useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import Modal, { Confirm, inputCls } from '@/components/Modal'
import { Button, PageHeader, Panel, Pill, Table } from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useMode, type Role } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'
import { ago, useFetch } from '@/lib/useFetch'

interface Invite { id: string; email: string; role: Role; expires_at: string; expired: boolean; created_at: string }
interface Member { id: string; console_user_id: string; name: string; email: string; role: Role; joined_at: string; last_active_at: string | null }
const ROLES: Role[] = ['admin', 'developer', 'reviewer', 'viewer']
const ROLE_HELP: Record<string, string> = {
  admin: 'Everything except removing owners', developer: 'API keys, webhooks, read everything',
  reviewer: 'Read users and verifications', viewer: 'Read-only',
}
const cap = (s: string) => s[0].toUpperCase() + s.slice(1)

export default function TeamPage() {
  const { org, can } = useMode()
  const { member: me } = useAuth()
  const base = org ? `/business/organisations/${org.id}/members` : null
  const { data, error, reload } = useFetch<Member[]>(base)
  const invites = useFetch<Invite[]>(org && can('admin') ? `/business/organisations/${org.id}/invites` : null)
  const invBase = org ? `/business/organisations/${org.id}/invites` : ''
  const [note, setNote] = useState('')
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<Member | null>(null)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('developer')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const isAdmin = can('admin')

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr('')
    try { await fn() } catch (e) { setErr(apiErrorMessage(e)) } finally { setBusy(false) }
  }
  const add = () => run(async () => {
    await api.post(invBase, { email: email.trim(), role }); await invites.reload(); setAdding(false)
    setNote(`Invite sent to ${email.trim()}`)
  })
  const resend = (i: Invite) => run(async () => { await api.post(`${invBase}/${i.id}/resend`); await invites.reload(); setNote(`New link sent to ${i.email}`) })
  const revoke = (i: Invite) => run(async () => { await api.delete(`${invBase}/${i.id}`); await invites.reload(); setNote(`Invite to ${i.email} cancelled`) })
  const changeRole = (m: Member, r: Role) => run(async () => { await api.patch(`${base}/${m.id}`, { role: r }); await reload() })
  const remove = (m: Member) => run(async () => { await api.delete(`${base}/${m.id}`); await reload(); setRemoving(null) })

  return (
    <div className="pb-8">
      <PageHeader title="Team" subtitle="Who on your side can access the FOID console">
        {isAdmin && <Button icon="ri-user-add-line" onClick={() => { setErr(''); setNote(''); setEmail(''); setAdding(true) }}>Invite member</Button>}
      </PageHeader>

      {err && !adding && !removing && <p className="mb-4 text-[13px] text-red-500">{err}</p>}
      {note && <p className="mb-4 text-[13px] text-green-600">{note}</p>}
      <Panel>
        <Table cols={['Member', 'Role', 'Status', 'Last active', '']}>
          {data?.map(m => {
            const editable = isAdmin && m.role !== 'owner' && m.console_user_id !== me?.id
            return (
              <tr key={m.id}>
                <td>
                  <div className="flex items-center gap-3">
                    <span className="w-11 h-11 rounded-lg bg-brand-100 flex items-center justify-center text-[15px] font-bold text-brand-600 shrink-0">
                      {m.name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase()}
                    </span>
                    <div>
                      <div className="font-semibold text-neutral-900">{m.name}{m.console_user_id === me?.id && <span className="text-neutral-400 font-normal"> (you)</span>}</div>
                      <div className="text-[12px] text-neutral-500">{m.email}</div>
                    </div>
                  </div>
                </td>
                <td>
                  {editable ? (
                    <select value={m.role} disabled={busy} onChange={e => void changeRole(m, e.target.value as Role)}
                      className="px-3 py-1.5 rounded-full border border-neutral-200 text-[12.5px] font-semibold bg-white">
                      {ROLES.map(r => <option key={r} value={r}>{cap(r)}</option>)}
                    </select>
                  ) : <Pill tone={m.role === 'owner' || m.role === 'admin' ? 'brand' : 'neutral'}>{cap(m.role)}</Pill>}
                </td>
                <td><Pill tone="success" dot>Active</Pill></td>
                <td className="whitespace-nowrap">{m.last_active_at ? ago(m.last_active_at) : 'Not yet'}</td>
                <td className="text-right">
                  {editable && (
                    <button aria-label={`Remove ${m.name}`} onClick={() => { setErr(''); setRemoving(m) }} className="p-1.5 rounded-full hover:bg-red-50">
                      <RemixIcon name="ri-user-unfollow-line" size={18} color="#ef4444" clickable />
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
          {invites.data?.map(i => (
            <tr key={i.id}>
              <td>
                <div className="flex items-center gap-3">
                  <span className="w-11 h-11 rounded-lg bg-[#C800DE] flex items-center justify-center shrink-0"><RemixIcon name="ri-mail-line" size={22} color="#fff" /></span>
                  <div>
                    <div className="font-semibold text-neutral-900">{i.email}</div>
                    <div className="text-[12px] text-neutral-500">Invited {ago(i.created_at)}</div>
                  </div>
                </div>
              </td>
              <td><Pill tone="neutral">{cap(i.role)}</Pill></td>
              <td>{i.expired ? <Pill tone="failed" dot>Link expired</Pill> : <Pill tone="warning" dot>Invited</Pill>}</td>
              <td>—</td>
              <td className="text-right whitespace-nowrap">
                <button aria-label={`Resend invite to ${i.email}`} title="Send a new link" disabled={busy} onClick={() => void resend(i)} className="p-1.5 rounded-full hover:bg-neutral-100">
                  <RemixIcon name="ri-refresh-line" size={18} clickable />
                </button>
                <button aria-label={`Cancel invite to ${i.email}`} title="Cancel invite" disabled={busy} onClick={() => void revoke(i)} className="p-1.5 rounded-full hover:bg-red-50">
                  <RemixIcon name="ri-close-circle-line" size={18} color="#ef4444" clickable />
                </button>
              </td>
            </tr>
          ))}
          {error && <tr><td colSpan={5} className="text-center !text-red-500 !py-10">{error}</td></tr>}
        </Table>
      </Panel>

      {adding && (
        <Modal title="Invite a team member" onClose={() => setAdding(false)}>
          <p className="text-[12.5px] text-neutral-500">
            We’ll email them a link that works for 7 days. If they don’t have a FOID Console account yet, they create one from the link.
          </p>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Work email
            <input className={inputCls} type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus />
          </label>
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Role</span>
            {ROLES.map(r => (
              <label key={r} className="flex items-start gap-2 text-[13px] cursor-pointer">
                <input type="radio" name="role" className="mt-1 accent-[#C800DE]" checked={role === r} onChange={() => setRole(r)} />
                <span><b>{cap(r)}</b> <span className="text-neutral-500">— {ROLE_HELP[r]}</span></span>
              </label>
            ))}
          </div>
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={!email.trim() || busy ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void add()}>{busy ? 'Sending…' : 'Send invite'}</Button></span>
        </Modal>
      )}
      {removing && (
        <Modal title="Remove member" onClose={() => setRemoving(null)}>
          <Confirm danger text={<><b>{removing.name}</b> loses access to {org?.name} right away. Their console account stays.</>}
            action="Remove" busy={busy} error={err} onCancel={() => setRemoving(null)} onConfirm={() => void remove(removing)} />
        </Modal>
      )}
    </div>
  )
}
