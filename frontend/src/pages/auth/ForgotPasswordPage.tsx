/**
 * Forgot Password — 3-step flow:
 *   Step 1: Enter email → POST /auth/forgot-password
 *   Step 2: Enter 6-digit OTP → POST /auth/verify-reset-code → receive reset_token
 *   Step 3: Enter new password → POST /auth/reset-password → redirect to /login
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import FoidWordmark from '@/components/FoidWordmark'

const BASE = '/api/v1/auth'

type Step = 'email' | 'otp' | 'reset' | 'done'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ── Step 1: send OTP ────────────────────────────────────────────────────
  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await axios.post(`${BASE}/forgot-password`, { email })
      setStep('otp')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2: verify OTP ──────────────────────────────────────────────────
  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (otp.length !== 6) {
      setError('Please enter the 6-digit code.')
      return
    }
    setLoading(true)
    try {
      const res = await axios.post(`${BASE}/verify-reset-code`, { email, code: otp })
      setResetToken((res.data as { reset_token: string }).reset_token)
      setStep('reset')
    } catch (err: unknown) {
      const detail =
        axios.isAxiosError(err) ? err.response?.data?.detail : null
      setError(detail ?? 'Invalid or expired code. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Step 3: reset password ──────────────────────────────────────────────
  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await axios.post(`${BASE}/reset-password`, {
        reset_token: resetToken,
        new_password: newPassword,
      })
      setStep('done')
    } catch (err: unknown) {
      const detail =
        axios.isAxiosError(err) ? err.response?.data?.detail : null
      setError(detail ?? 'Could not reset password. Please start again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="relative w-screen h-screen overflow-hidden flex items-center justify-center md:justify-end"
      style={{
        backgroundImage: `url('/login.jpg')`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        backgroundColor: '#C800DE',
      }}
    >
      {/* Purple gradient overlay */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, rgba(200,0,222,0) 0%, #6C0078 100%)' }}
      />

      <div
        className="relative z-10 w-screen h-screen flex items-center justify-center md:justify-end"
        style={{ padding: 'clamp(12px, 3vh, 40px) clamp(16px, 5vw, 160px)' }}
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
          {/* Logo */}
          <div className="flex items-center gap-2" style={{ marginBottom: 'clamp(16px, 3vh, 32px)' }}>
            <img src="/logo.png" alt="FOID logo" className="h-7 w-auto object-contain" />
            <FoidWordmark color="#18181b" height={20} />
          </div>

          {/* ── Step indicator ── */}
          {step !== 'done' && (
            <div className="flex items-center gap-2 mb-6">
              {(['email', 'otp', 'reset'] as Step[]).map((s, i) => (
                <div key={s} className="flex items-center gap-2">
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-bold transition-colors"
                    style={{
                      background: step === s || (
                        (s === 'email' && (step === 'otp' || step === 'reset')) ||
                        (s === 'otp' && step === 'reset')
                      ) ? 'linear-gradient(90deg,#C800DE,#9000A8)' : '#f3f4f6',
                      color: step === s || (
                        (s === 'email' && (step === 'otp' || step === 'reset')) ||
                        (s === 'otp' && step === 'reset')
                      ) ? '#fff' : '#9ca3af',
                    }}
                  >
                    {i + 1}
                  </div>
                  {i < 2 && (
                    <div className="w-8 h-px" style={{ background: '#e5e7eb' }} />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── STEP 1: Email ── */}
          {step === 'email' && (
            <>
              <h1 className="text-[26px] font-extrabold text-neutral-900 tracking-tight mb-2">
                Reset your password
              </h1>
              <p className="text-[13px] text-neutral-400 mb-7">
                Enter your account email and we'll send you a 6-digit reset code.
              </p>
              {error && <ErrorBox message={error} />}
              <form onSubmit={handleSendCode} className="flex flex-col gap-5">
                <Field label="Email Address" required>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="bobdylan@gmail.com"
                    required
                    className="w-full border border-neutral-200 rounded-lg px-4 py-3 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
                  />
                </Field>
                <SubmitButton loading={loading} label="Send reset code" />
                <BackToLogin />
              </form>
            </>
          )}

          {/* ── STEP 2: OTP ── */}
          {step === 'otp' && (
            <>
              <h1 className="text-[26px] font-extrabold text-neutral-900 tracking-tight mb-2">
                Check your email
              </h1>
              <p className="text-[13px] text-neutral-400 mb-7">
                We sent a 6-digit code to{' '}
                <span className="font-semibold text-neutral-700">{email}</span>.
                It expires in 10 minutes.
              </p>
              {error && <ErrorBox message={error} />}
              <form onSubmit={handleVerifyOtp} className="flex flex-col gap-5">
                <Field label="Reset code" required>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={otp}
                    onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="123456"
                    required
                    className="w-full border border-neutral-200 rounded-lg px-4 py-3 text-[22px] font-mono tracking-[0.5em] text-neutral-900 placeholder:text-neutral-300 placeholder:text-[14px] placeholder:tracking-normal outline-none focus:border-[#C800DE] transition-colors bg-white text-center"
                  />
                </Field>
                <SubmitButton loading={loading} label="Verify code" />
                <button
                  type="button"
                  onClick={() => { setStep('email'); setOtp(''); setError('') }}
                  className="text-[13px] text-neutral-400 hover:text-[#C800DE] transition-colors text-center"
                >
                  ← Use a different email
                </button>
              </form>
            </>
          )}

          {/* ── STEP 3: New password ── */}
          {step === 'reset' && (
            <>
              <h1 className="text-[26px] font-extrabold text-neutral-900 tracking-tight mb-2">
                Set a new password
              </h1>
              <p className="text-[13px] text-neutral-400 mb-7">
                Must be at least 8 characters with uppercase, lowercase, number, and special character.
              </p>
              {error && <ErrorBox message={error} />}
              <form onSubmit={handleReset} className="flex flex-col gap-5">
                <Field label="New password" required>
                  <div className="relative">
                    <input
                      type={showPwd ? 'text' : 'password'}
                      value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      placeholder="••••••••"
                      required
                      className="w-full border border-neutral-200 rounded-lg px-4 py-3 pr-11 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
                    />
                    <EyeToggle show={showPwd} onToggle={() => setShowPwd(v => !v)} />
                  </div>
                </Field>
                <Field label="Confirm new password" required>
                  <input
                    type={showPwd ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full border border-neutral-200 rounded-lg px-4 py-3 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
                  />
                </Field>
                <SubmitButton loading={loading} label="Reset password" />
              </form>
            </>
          )}

          {/* ── Done ── */}
          {step === 'done' && (
            <div className="flex flex-col items-center text-center gap-5 py-6">
              {/* Checkmark */}
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg,#C800DE,#9000A8)' }}
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div>
                <h2 className="text-[24px] font-extrabold text-neutral-900 mb-2">Password reset!</h2>
                <p className="text-[13px] text-neutral-400">
                  Your password has been updated. You can now log in with your new password.
                </p>
              </div>
              <button
                onClick={() => navigate('/login')}
                className="w-full py-3.5 rounded-xl text-white font-bold text-[15px] tracking-wide transition-opacity hover:opacity-90"
                style={{ background: 'linear-gradient(90deg,#C800DE,#9000A8)' }}
              >
                Go to Login
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Small shared sub-components ──────────────────────────────────────────────

function Field({ label, required, children }: {
  label: string; required?: boolean; children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[13px] font-semibold text-neutral-900">
        {label}{required && <span className="text-red-600 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-2">
      <p className="text-[13px] text-red-600">{message}</p>
    </div>
  )
}

function SubmitButton({ loading, label }: { loading: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="w-full py-3.5 rounded-xl text-white font-bold text-[15px] tracking-wide transition-opacity hover:opacity-90 disabled:opacity-60"
      style={{ background: 'linear-gradient(90deg,#C800DE,#9000A8)' }}
    >
      {loading ? 'Please wait…' : label}
    </button>
  )
}

function BackToLogin() {
  return (
    <p className="text-center text-[13px] text-neutral-600">
      Remember it?{' '}
      <Link to="/login" className="text-[#C800DE] font-bold hover:opacity-80 transition-opacity">
        Back to Login
      </Link>
    </p>
  )
}

function EyeToggle({ show, onToggle }: { show: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={show ? 'Hide password' : 'Show password'}
      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-[#C800DE] transition-colors"
    >
      {show ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      )}
    </button>
  )
}
