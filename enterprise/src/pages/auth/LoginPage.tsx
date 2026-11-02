import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import AuthShell, { AuthInput, SubmitButton } from '@/components/AuthShell'
import { useAuth } from '@/contexts/AuthContext'

export default function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next')?.startsWith('/') ? params.get('next')! : '/'   // only same-site paths
  const { login, completeMfa, member } = useAuth()
  const [form, setForm] = useState({ email: params.get('email') ?? '', password: '' })
  const [mfa, setMfa] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (member) navigate(next, { replace: true }) }, [member, navigate, next])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    const r = await login(form.email, form.password)
    setBusy(false)
    if ('mfa' in r && r.mfa) { setMfa(r.mfa); return }
    if (!r.ok) setError(r.error ?? '')
  }
  const submitCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    const r = await completeMfa(mfa!, code)
    setBusy(false)
    if (!r.ok) { setError(r.error); setCode('') }
  }

  if (mfa) {
    return (
      <AuthShell error={error} title="Two-step sign-in" subtitle="Enter the 6-digit code from your authenticator app.">
        <form onSubmit={submitCode} className="flex flex-col gap-5">
          <AuthInput label="Authenticator code" inputMode="numeric" autoComplete="one-time-code" placeholder="123456" maxLength={6} autoFocus
            value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
          <SubmitButton disabled={code.length !== 6 || busy}>{busy ? 'Checking…' : 'Sign in'}</SubmitButton>
          <button type="button" onClick={() => { setMfa(null); setCode(''); setError('') }} className="text-[13px] font-semibold text-neutral-500">
            Back
          </button>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell error={error} title="Sign in to FOID Console"
      subtitle="Manage verifications, API keys and your team. This is separate from a personal FOID account.">
      <form onSubmit={submit} className="flex flex-col gap-5">
        <AuthInput label="Work email" type="email" required autoComplete="email" placeholder="ada@company.com"
          value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        <div className="flex flex-col gap-1.5">
          <AuthInput label="Password" type="password" required autoComplete="current-password" placeholder="••••••••"
            value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
          <Link to="/forgot-password" className="text-[13px] font-semibold text-[#C800DE] hover:opacity-80">Forgot password?</Link>
        </div>
        <SubmitButton disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</SubmitButton>
        <p className="text-center text-[13px] text-neutral-600">
          New to FOID for business? <Link to="/signup" className="text-[#C800DE] font-bold hover:opacity-80">Create a business account</Link>
        </p>
      </form>
    </AuthShell>
  )
}
