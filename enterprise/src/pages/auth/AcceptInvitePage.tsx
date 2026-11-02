/** /invite/:token — join a business from an emailed invite (creates the console account if needed). */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AuthShell, { AuthInput, PasswordRules, PWD_RULES, SubmitButton } from '@/components/AuthShell'
import { useAuth } from '@/contexts/AuthContext'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'

interface Info { org_name: string; role: string; email: string; has_account: boolean; invited_by: string | null }

export default function AcceptInvitePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const { member, loading, adoptTokens, logout } = useAuth()
  const { reloadOrgs, selectOrg } = useMode()
  const [info, setInfo] = useState<Info | null>(null)
  const [fatal, setFatal] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({ first_name: '', last_name: '', password: '' })

  useEffect(() => {
    api.get<Info>(`/console/invites/${token}`).then(r => setInfo(r.data)).catch(e => setFatal(apiErrorMessage(e, 'This invite link isn’t valid.')))
  }, [token])

  const accept = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try {
      const r = (await api.post<{ org_id: string; access_token?: string; refresh_token?: string }>(`/console/invites/${token}/accept`,
        info?.has_account ? {} : f)).data
      if (r.access_token && r.refresh_token) await adoptTokens(r.access_token, r.refresh_token)
      await reloadOrgs().catch(() => {})
      selectOrg(r.org_id)
      navigate('/', { replace: true })
    } catch (err) { setError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  if (fatal) {
    return (
      <AuthShell title="Invite unavailable" subtitle={fatal}>
        <Link to="/login" className="text-[13px] font-semibold text-[#C800DE]">Go to sign in</Link>
      </AuthShell>
    )
  }
  if (!info || loading) return <AuthShell title="Loading invite…" subtitle=" "><span /></AuthShell>

  const title = `Join ${info.org_name}`
  const sub = <>{info.invited_by ? `${info.invited_by} invited` : 'You were invited'} <b className="text-neutral-800">{info.email}</b> as <b className="text-neutral-800">{info.role}</b>.</>

  if (info.has_account) {
    const rightUser = member?.email.toLowerCase() === info.email
    return (
      <AuthShell title={title} subtitle={sub} error={error}>
        {rightUser ? (
          <form onSubmit={accept} className="flex flex-col gap-4"><SubmitButton disabled={busy}>{busy ? 'Joining…' : `Join ${info.org_name}`}</SubmitButton></form>
        ) : (
          <div className="flex flex-col gap-3 text-[13px]">
            {member && <p className="text-neutral-600">You’re signed in as {member.email}. This invite is for {info.email}.</p>}
            <button onClick={() => void logout().then(() => navigate(`/login?email=${encodeURIComponent(info.email)}&next=${encodeURIComponent(`/invite/${token}`)}`))}
              className="w-full py-3.5 rounded-xl text-white font-bold text-[15px]" style={{ background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)' }}>
              Sign in as {info.email}
            </button>
          </div>
        )}
      </AuthShell>
    )
  }

  const ready = f.first_name.trim() && f.last_name.trim() && PWD_RULES.every(r => r.test(f.password))
  return (
    <AuthShell title={title} subtitle={<>{sub} Create your console account to continue.</>} error={error}>
      <form onSubmit={accept} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <AuthInput label="First name" autoComplete="given-name" value={f.first_name} onChange={e => setF(p => ({ ...p, first_name: e.target.value }))} />
          <AuthInput label="Last name" autoComplete="family-name" value={f.last_name} onChange={e => setF(p => ({ ...p, last_name: e.target.value }))} />
        </div>
        <AuthInput label="Work email" value={info.email} disabled readOnly />
        <AuthInput label="Password" type="password" autoComplete="new-password" value={f.password} onChange={e => setF(p => ({ ...p, password: e.target.value }))} />
        {f.password && <PasswordRules password={f.password} />}
        <SubmitButton disabled={!ready || busy}>{busy ? 'Joining…' : `Create account and join`}</SubmitButton>
      </form>
    </AuthShell>
  )
}
