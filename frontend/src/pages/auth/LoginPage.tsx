import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, isAuthenticated } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ email: '', password: '' })

  // Redirect if already authenticated
  if (isAuthenticated) {
    navigate('/dashboard', { replace: true })
  }

  const set = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const success = await login(form.email, form.password)

    if (success) {
      navigate('/dashboard')
    } else {
      setError('Invalid email or password')
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
      {/* Purple gradient overlay — bottom fade same as signup */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, rgba(200, 0, 222, 0) 0%, #6C0078 100%)' }}
      />

      {/* Card wrapper */}
      <div
        className="relative z-10 w-screen h-screen flex items-center justify-center md:justify-end"
        style={{ padding: 'clamp(12px, 3vh, 40px) clamp(16px, 5vw, 160px)', height: '100%' }}
      >
        {/* White card */}
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
            <span
              className="text-[21px] font-extrabold text-neutral-900 tracking-tight"
              style={{ fontFamily: "'Neue Machina', sans-serif" }}
            >
              Foid
            </span>
          </div>

          {/* Heading */}
          <h1
            className="text-[28px] leading-[1.2] font-extrabold text-neutral-900 tracking-tight"
            style={{ marginBottom: 10 }}
          >
            Welcome<br />back to FOID
          </h1>
          <p
            className="text-[13px] text-neutral-400 leading-relaxed"
            style={{ marginBottom: 'clamp(20px, 3.5vh, 36px)' }}
          >
            Access your financial identity, manage consent, and<br />
            view your AI-powered ledger.
          </p>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4">
              <p className="text-[13px] text-red-600">{error}</p>
            </div>
          )}

          {/* Form */}
          <form
            onSubmit={handleSubmit}
            noValidate
            className="flex flex-col"
            style={{ gap: 'clamp(14px, 2.4vh, 24px)' }}
          >
            {/* Email */}
            <Field label="Email Address" required>
              <input
                id="login-email"
                name="email"
                type="email"
                placeholder="name@company.com"
                value={form.email}
                onChange={set}
                required
                className="w-full border border-neutral-200 rounded-lg px-4 py-3 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
              />
            </Field>

            {/* Password */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[13px] font-semibold text-neutral-900">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••"
                  value={form.password}
                  onChange={set}
                  required
                  className="w-full border border-neutral-200 rounded-lg px-4 py-3 pr-11 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white"
                />
                <button
                  type="button"
                  id="toggle-login-password"
                  onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-[#C800DE] transition-colors"
                >
                  {showPassword ? (
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
              </div>

              {/* Forgot password — sits right below the input */}
              <a
                href="#"
                id="forgot-password-link"
                className="text-[13px] font-semibold text-[#C800DE] hover:opacity-80 transition-opacity mt-0.5"
              >
                Forgot Password?
              </a>
            </div>

            {/* Submit */}
            <button
              id="login-submit"
              type="submit"
              className="w-full py-3.5 rounded-xl text-white font-bold text-[15px] tracking-wide transition-opacity hover:opacity-90"
              style={{ background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)' }}
            >
              Log In
            </button>

            {/* Create account */}
            <p className="text-center text-[13px] text-neutral-600">
              Don't have an account?{' '}
              <Link
                to="/signup"
                className="text-[#C800DE] font-bold hover:opacity-80 transition-opacity"
              >
                Create your FOID
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}

/* ── Shared field wrapper ───────────────────────────────────────────────── */
function Field({
  label, required, children,
}: {
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
