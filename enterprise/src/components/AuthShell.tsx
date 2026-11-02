/** Background + white card used by every console auth page (layout from frontend/ LoginPage). */
import { useState, type ReactNode } from 'react'
import FoidWordmark from './FoidWordmark'
import RemixIcon from './RemixIcon'

export default function AuthShell({ title, subtitle, image = '/login.jpg', error, children }: {
  title: ReactNode; subtitle: ReactNode; image?: string; error?: string; children: ReactNode
}) {
  return (
    <div className="relative w-screen min-h-screen flex items-center justify-center md:justify-end"
      style={{ backgroundImage: `url('${image}')`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundColor: '#C800DE' }}>
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(180deg, rgba(200, 0, 222, 0) 0%, #6C0078 100%)' }} />
      <div className="relative z-10 w-full flex items-center justify-center md:justify-end"
        style={{ padding: 'clamp(12px, 3vh, 40px) clamp(16px, 5vw, 160px)' }}>
        <div className="bg-white w-full" style={{ maxWidth: 560, borderRadius: 24, padding: 'clamp(20px, 4vh, 48px) clamp(20px, 4vw, 52px)', boxShadow: '0 8px 40px rgba(0,0,0,0.18)' }}>
          <div className="flex items-center gap-2 mb-6">
            <img src="/logo.png" alt="FOID logo" className="h-7 w-auto object-contain" />
            <FoidWordmark color="#18181b" height={20} />
            <span className="ml-1 px-2 py-0.5 rounded-full bg-brand-100 text-brand-600 text-[11px] font-bold uppercase tracking-wider">Console</span>
          </div>
          <h1 className="text-[26px] leading-[1.2] font-extrabold text-neutral-900 tracking-tight mb-2">{title}</h1>
          <p className="text-[13px] text-neutral-500 leading-relaxed mb-6">{subtitle}</p>
          {error && <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4 text-[13px] text-red-600">{error}</div>}
          {children}
        </div>
      </div>
    </div>
  )
}

const inputCls = 'w-full border border-neutral-200 rounded-lg px-4 py-3 text-[13px] text-neutral-900 placeholder:text-neutral-400 outline-none focus:border-[#C800DE] transition-colors bg-white'

export function AuthInput({ label, type = 'text', ...rest }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false)
  const isPw = type === 'password'
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-neutral-900">{label}</span>
      <span className="relative">
        <input {...rest} type={isPw && show ? 'text' : type} className={`${inputCls} ${isPw ? 'pr-11' : ''}`} />
        {isPw && (
          <button type="button" onClick={() => setShow(s => !s)} aria-label={show ? 'Hide password' : 'Show password'}
            className="absolute right-3.5 top-1/2 -translate-y-1/2">
            <RemixIcon name={show ? 'ri-eye-off-line' : 'ri-eye-line'} size={17} color="#a1a1aa" clickable />
          </button>
        )}
      </span>
    </label>
  )
}

export function SubmitButton({ children, disabled }: { children: ReactNode; disabled?: boolean }) {
  return (
    <button type="submit" disabled={disabled}
      className="w-full py-3.5 rounded-xl text-white font-bold text-[15px] transition-opacity hover:opacity-90 disabled:opacity-50"
      style={{ background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)' }}>
      {children}
    </button>
  )
}

/** Live checklist under the password field — mirrors backend console_auth._password_rule. */
export const PWD_RULES = [
  { label: 'At least 8 characters', test: (p: string) => p.length >= 8 },
  { label: 'One uppercase letter', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'One lowercase letter', test: (p: string) => /[a-z]/.test(p) },
  { label: 'One number', test: (p: string) => /[0-9]/.test(p) },
  { label: 'One special character', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
]

export function PasswordRules({ password }: { password: string }) {
  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-1 -mt-1">
      {PWD_RULES.map(r => {
        const ok = r.test(password)
        return (
          <li key={r.label} className={`flex items-center gap-1.5 text-[12px] ${ok ? 'text-green-600' : 'text-neutral-400'}`}>
            <RemixIcon name={ok ? 'ri-checkbox-circle-fill' : 'ri-checkbox-blank-circle-line'} size={13} /> {r.label}
          </li>
        )
      })}
    </ul>
  )
}
