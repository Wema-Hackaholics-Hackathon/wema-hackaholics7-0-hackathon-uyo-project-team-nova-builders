import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthShell, { AuthInput, PasswordRules, PWD_RULES, SubmitButton } from '@/components/AuthShell'
import { api, apiErrorMessage } from '@/lib/api'

/** Two steps: email → (code + new password). Resetting signs the account out everywhere. */
export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<'email' | 'reset'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) { setError(apiErrorMessage(e)) } finally { setBusy(false) }
  }

  const sendCode = (e: React.FormEvent) => {
    e.preventDefault()
    void run(async () => { await api.post('/console/auth/forgot-password', { email }); setStep('reset') })
  }
  const reset = (e: React.FormEvent) => {
    e.preventDefault()
    void run(async () => {
      await api.post('/console/auth/reset-password', { email, code, new_password: password })
      navigate('/login', { replace: true })
    })
  }

  return step === 'email' ? (
    <AuthShell error={error} title="Reset your console password" subtitle="Enter the email you use for FOID Console. We’ll send a 6-digit code.">
      <form onSubmit={sendCode} className="flex flex-col gap-5">
        <AuthInput label="Work email" type="email" required value={email} onChange={e => setEmail(e.target.value)} />
        <SubmitButton disabled={!email || busy}>{busy ? 'Sending…' : 'Send code'}</SubmitButton>
        <Link to="/login" className="text-center text-[13px] font-semibold text-[#C800DE]">Back to sign in</Link>
      </form>
    </AuthShell>
  ) : (
    <AuthShell error={error} title="Set a new password"
      subtitle={<>If a console account uses <b className="text-neutral-800">{email}</b>, a code is on its way. It expires in 10 minutes.</>}>
      <form onSubmit={reset} className="flex flex-col gap-4">
        <AuthInput label="Code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456"
          value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
        <AuthInput label="New password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
        {password && <PasswordRules password={password} />}
        <SubmitButton disabled={code.length !== 6 || !PWD_RULES.every(r => r.test(password)) || busy}>
          {busy ? 'Saving…' : 'Save new password'}
        </SubmitButton>
        <button type="button" onClick={() => setStep('email')} className="text-[13px] font-semibold text-neutral-500">Use a different email</button>
      </form>
    </AuthShell>
  )
}
