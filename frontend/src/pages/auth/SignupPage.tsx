import { useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import FoidWordmark from '@/components/FoidWordmark'

/* ── Password strength rules — mirrors backend-2/app/schemas/auth.py ── */
const PWD_RULES = [
  { key: 'length',  label: 'At least 8 characters',       test: (p: string) => p.length >= 8 },
  { key: 'upper',   label: 'One uppercase letter (A–Z)',   test: (p: string) => /[A-Z]/.test(p) },
  { key: 'lower',   label: 'One lowercase letter (a–z)',   test: (p: string) => /[a-z]/.test(p) },
  { key: 'number',  label: 'One number (0–9)',              test: (p: string) => /[0-9]/.test(p) },
  { key: 'special', label: 'One special character (!@#…)', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
] as const

export default function SignupPage() {
  const navigate = useNavigate()
  const { signup, isAuthenticated } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm,  setShowConfirm]  = useState(false)
  const [agreed, setAgreed]             = useState(false)
  const [error, setError]               = useState('')
  const [pwdTouched, setPwdTouched]     = useState(false)
  const [cfmTouched, setCfmTouched]     = useState(false)
  const [form, setForm] = useState({
    firstName: '', lastName: '', middleName: '',
    nin: '', email: '', password: '', confirmPassword: '',
  })

  // Redirect if already authenticated
  if (isAuthenticated) {
    navigate('/dashboard', { replace: true })
  }

  const set = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))

  /* ── Derived validation ───────────────────────────────────────────── */
  const pwdChecks = useMemo(
    () => PWD_RULES.map(r => ({ ...r, pass: r.test(form.password) })),
    [form.password],
  )
  const allPwdPass     = pwdChecks.every(c => c.pass)
  const passwordsMatch = form.confirmPassword.length > 0 && form.password === form.confirmPassword

  const requiredFilled =
    form.firstName.trim() !== '' &&
    form.lastName.trim()  !== '' &&
    form.nin.trim()       !== '' &&
    form.email.trim()     !== ''

  const canSubmit = requiredFilled && allPwdPass && passwordsMatch && agreed

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setError('')

    const success = await signup({
      firstName: form.firstName,
      lastName: form.lastName,
      middleName: form.middleName || undefined,
      nin: form.nin,
      email: form.email,
      password: form.password,
    })

    if (success) {
      navigate('/dashboard')
    } else {
      setError('An account with this email already exists')
    }
  }

  return (
    <div
      className="relative w-screen h-screen overflow-hidden flex items-center justify-center md:justify-end"
      style={{
        backgroundImage: `url('/signup.jpg')`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        backgroundColor: '#6C0078',
      }}
    >
		<div
        className="absolute inset-0 pointer-events-none"
        style={{
          backdropFilter: 'blur(500px)',
          WebkitBackdropFilter: 'blur(500px)',
          maskImage: 'linear-gradient(90deg, transparent 0%, transparent 38%, black 72%)',
          WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, transparent 38%, black 72%)',
        }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, rgba(200, 0, 222, 0) 0%, #6C0078 100%)' }}
      />

      <div
        className="relative w-screen h-screen overflow-hidden flex items-center justify-center md:justify-end"
        style={{ padding: 'clamp(12px, 3vh, 40px) clamp(16px, 5vw, 160px)', height: '100%' }}
      >
        <div
          className="bg-white w-full overflow-y-auto"
          style={{
            maxWidth: 705,
            maxHeight: '100%',
            borderRadius: 24,
            padding: 'clamp(20px, 4vh, 55px) clamp(20px, 4vw, 58px)',
            boxShadow: '0 8px 40px rgba(0,0,0,0.18)',
          }}
        >
          <div className="flex items-center gap-2" style={{ marginBottom: 'clamp(12px, 2vh, 24px)' }}>
            <img src="/logo.png" alt="FOID logo" className="h-7 w-auto object-contain" />
            <FoidWordmark color="#18181b" height={20} />
          </div>

          <h1
            className="text-[26px] leading-[1.2] font-extrabold text-neutral-900 tracking-tight"
            style={{ marginBottom: 8 }}
          >
            Create your<br />portable financial identity.
          </h1>
          <p
            className="text-[12.5px] text-neutral-400 leading-relaxed"
            style={{ marginBottom: 'clamp(12px, 2vh, 24px)' }}
          >
            Verify your identity once. Securely connect your bank accounts and access
            fintech platforms instantly with a single click.
          </p>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4">
              <p className="text-[13px] text-red-600">{error}</p>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            noValidate
            className="flex flex-col"
            style={{ gap: 'clamp(14px, 2.4vh, 31px)' }}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="First name" required>
                <Input id="first-name" name="firstName" placeholder="John"
                  value={form.firstName} onChange={set} required />
              </Field>
              <Field label="Last name" required>
                <Input id="last-name" name="lastName" placeholder="Doe"
                  value={form.lastName} onChange={set} required />
              </Field>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Middle name">
                <Input id="middle-name" name="middleName" placeholder="Bob"
                  value={form.middleName} onChange={set} />
              </Field>
              <Field label="NIN" required>
                <Input id="nin" name="nin" placeholder="23365001238"
                  value={form.nin} onChange={set} required />
              </Field>
            </div>

            <Field label="Email address" required>
              <Input id="email" name="email" type="email" placeholder="bobdylan@gmail.com"
                value={form.email} onChange={set} required />
            </Field>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Field label="Password" required>
                  <PasswordInput
                    id="password" name="password"
                    show={showPassword} toggle={() => setShowPassword(v => !v)}
                    value={form.password} onChange={set}
                    onFocus={() => setPwdTouched(true)}
                  />
                </Field>
                {pwdTouched && (
                  <ul className="flex flex-col gap-1 mt-1">
                    {pwdChecks.map(c => (
                      <li key={c.key} className="flex items-center gap-1.5">
                        <span className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full shrink-0 ${c.pass ? 'bg-[#C800DE]' : 'bg-red-500'}`}>
                          {c.pass ? (
                            <svg width="7" height="6" viewBox="0 0 7 6" fill="none">
                              <path d="M1 3L2.8 5L6 1" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          ) : (
                            <svg width="7" height="7" viewBox="0 0 7 7" fill="none">
                              <path d="M1.5 1.5L5.5 5.5M5.5 1.5L1.5 5.5" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
                            </svg>
                          )}
                        </span>
                        <span className={`text-[11px] ${c.pass ? 'text-[#C800DE]' : 'text-red-500'}`}>{c.label}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <Field label="Confirm Password" required>
                  <PasswordInput
                    id="confirm-password" name="confirmPassword"
                    show={showConfirm} toggle={() => setShowConfirm(v => !v)}
                    value={form.confirmPassword} onChange={set}
                    onFocus={() => setCfmTouched(true)}
                  />
                </Field>
                {cfmTouched && form.confirmPassword.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full shrink-0 ${passwordsMatch ? 'bg-[#C800DE]' : 'bg-red-500'}`}>
                      {passwordsMatch ? (
                        <svg width="7" height="6" viewBox="0 0 7 6" fill="none">
                          <path d="M1 3L2.8 5L6 1" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      ) : (
                        <svg width="7" height="7" viewBox="0 0 7 7" fill="none">
                          <path d="M1.5 1.5L5.5 5.5M5.5 1.5L1.5 5.5" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
                        </svg>
                      )}
                    </span>
                    <span className={`text-[11px] ${passwordsMatch ? 'text-[#C800DE]' : 'text-red-500'}`}>
                      {passwordsMatch ? 'Passwords match' : 'Passwords do not match'}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                id="tos-checkbox"
                role="checkbox"
                aria-checked={agreed}
                onClick={() => setAgreed(v => !v)}
                className="w-5 h-5 min-w-[20px] rounded-full border-2 border-[#C800DE] flex items-center justify-center transition-colors shrink-0"
                style={{ background: agreed ? '#C800DE' : 'transparent' }}
              >
                {agreed && (
                  <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                    <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.8"
                      strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
              <span className="text-[13px] text-neutral-600">
                I agree to the{' '}
                <a href="#" className="text-[#C800DE] font-semibold hover:opacity-80 transition-opacity">
                  Terms of Service
                </a>
                {' '}and{' '}
                <a href="#" className="text-[#C800DE] font-semibold hover:opacity-80 transition-opacity">
                  Privacy Policy.
                </a>
              </span>
            </div>

            <button
              id="signup-submit"
              type="submit"
              disabled={!canSubmit}
              className="w-full py-3.5 rounded-xl text-white font-bold text-[15px] tracking-wide transition-all"
              style={{
                background: canSubmit
                  ? 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)'
                  : undefined,
                backgroundColor: canSubmit ? undefined : '#d1d5db',
                cursor: canSubmit ? 'pointer' : 'not-allowed',
                opacity: 1,
              }}
            >
              Sign Up
            </button>

            <p className="text-center text-[13px] text-neutral-600">
              Already have a FOID?{' '}
              <Link to="/login" className="text-[#C800DE] font-bold hover:opacity-80 transition-opacity">
                Log in here
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}

/* ── Local sub-components ───────────────────────────────────────────────── */

function Field({
  label, required, children,
}: {
  label: string; required?: boolean; children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[12.5px] font-semibold text-neutral-900">
        {label}{required && <span className="text-red-600 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

function Input({
  id, ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { id: string }) {
  return (
    <input
      id={id}
      className="w-full border border-neutral-200 rounded-lg px-3.5 py-2.5 text-[12.5px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
      {...props}
    />
  )
}

function PasswordInput({
  id, name, show, toggle, value, onChange, onFocus,
}: {
  id: string; name: string; show: boolean
  toggle: () => void; value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onFocus?: () => void
}) {
  return (
    <div className="relative">
      <input
        id={id}
        name={name}
        type={show ? 'text' : 'password'}
        placeholder="••••••••"
        value={value}
        onChange={onChange}
        onFocus={onFocus}
        className="w-full border border-neutral-200 rounded-lg px-3.5 py-2.5 pr-10 text-[12.5px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
      />
      <button
        type="button"
        id={`toggle-${id}`}
        onClick={toggle}
        aria-label={show ? 'Hide password' : 'Show password'}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-[#C800DE] transition-colors"
      >
        {show ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  )
}