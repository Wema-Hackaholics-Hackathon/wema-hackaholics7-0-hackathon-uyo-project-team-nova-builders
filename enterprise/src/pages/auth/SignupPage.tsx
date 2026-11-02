import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthShell, { AuthInput, PasswordRules, PWD_RULES, SubmitButton } from '@/components/AuthShell'
import { useAuth } from '@/contexts/AuthContext'

export default function SignupPage() {
  const navigate = useNavigate()
  const { signup, member } = useAuth()
  const [f, setF] = useState({ first_name: '', last_name: '', company_name: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF(p => ({ ...p, [k]: e.target.value }))

  useEffect(() => { if (member) navigate(member.email_verified ? '/' : '/verify-email', { replace: true }) }, [member, navigate])

  const pwOk = PWD_RULES.every(r => r.test(f.password))
  const match = f.confirm.length > 0 && f.confirm === f.password
  const ready = f.first_name.trim() && f.last_name.trim() && f.company_name.trim().length >= 2 && f.email.trim() && pwOk && match

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true); setError('')
    const { confirm: _confirm, ...body } = f
    const r = await signup(body)
    setBusy(false)
    if (!r.ok) setError(r.error)
  }

  return (
    <AuthShell image="/signup.jpg" error={error} title="Create your business account"
      subtitle="Start in Test mode with sandbox keys straight away. Go live after we review your business documents.">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <AuthInput label="First name" required autoComplete="given-name" value={f.first_name} onChange={set('first_name')} />
          <AuthInput label="Last name" required autoComplete="family-name" value={f.last_name} onChange={set('last_name')} />
        </div>
        <AuthInput label="Company name" required autoComplete="organization" placeholder="Sterling Microfinance Bank"
          value={f.company_name} onChange={set('company_name')} />
        <AuthInput label="Work email" type="email" required autoComplete="email" placeholder="ada@company.com"
          value={f.email} onChange={set('email')} />
        <AuthInput label="Password" type="password" required autoComplete="new-password" value={f.password} onChange={set('password')} />
        {f.password && <PasswordRules password={f.password} />}
        <AuthInput label="Confirm password" type="password" required autoComplete="new-password" value={f.confirm} onChange={set('confirm')} />
        {f.confirm && <p className={`-mt-2 text-[12px] ${match ? 'text-green-600' : 'text-red-500'}`}>{match ? 'Passwords match' : 'Passwords don’t match'}</p>}
        <SubmitButton disabled={!ready || busy}>{busy ? 'Creating account…' : 'Create account'}</SubmitButton>
        <p className="text-center text-[13px] text-neutral-600">
          Already have a console account? <Link to="/login" className="text-[#C800DE] font-bold hover:opacity-80">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  )
}
