import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import AuthShell, { AuthInput, SubmitButton } from '@/components/AuthShell'
import { useAuth } from '@/contexts/AuthContext'

export default function VerifyEmailPage() {
  const navigate = useNavigate()
  const { member, loading, verifyEmail, resendVerification, logout } = useAuth()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (member?.email_verified) navigate('/', { replace: true }) }, [member, navigate])
  if (!loading && !member) return <Navigate to="/login" replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(''); setNote('')
    const r = await verifyEmail(code)
    setBusy(false)
    if (!r.ok) setError(r.error)
  }
  const resend = async () => {
    setError(''); setNote('')
    const r = await resendVerification()
    if (r.ok) setNote('A new code is on its way.')
    else setError(r.error)
  }

  return (
    <AuthShell error={error} title="Check your email"
      subtitle={<>We sent a 6-digit code to <b className="text-neutral-800">{member?.email}</b>. It expires in 30 minutes.</>}>
      <form onSubmit={submit} className="flex flex-col gap-5">
        <AuthInput label="Verification code" inputMode="numeric" autoComplete="one-time-code" placeholder="123456" maxLength={6}
          value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
        {note && <p className="-mt-3 text-[12.5px] text-green-600">{note}</p>}
        <SubmitButton disabled={code.length !== 6 || busy}>{busy ? 'Checking…' : 'Verify email'}</SubmitButton>
        <div className="flex justify-between text-[13px]">
          <button type="button" onClick={() => void resend()} className="font-semibold text-[#C800DE]">Send a new code</button>
          <button type="button" onClick={() => void logout().then(() => navigate('/login'))} className="text-neutral-500">Use another account</button>
        </div>
      </form>
    </AuthShell>
  )
}
