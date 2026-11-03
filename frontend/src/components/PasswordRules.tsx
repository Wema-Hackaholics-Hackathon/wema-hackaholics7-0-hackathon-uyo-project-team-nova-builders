/** Password rules (mirror backend/app/schemas/auth.py) + the ✓/✗ checklist shown while typing. */

export const PWD_RULES = [
  { key: 'length',  label: 'At least 8 characters',       test: (p: string) => p.length >= 8 },
  { key: 'upper',   label: 'One uppercase letter (A–Z)',   test: (p: string) => /[A-Z]/.test(p) },
  { key: 'lower',   label: 'One lowercase letter (a–z)',   test: (p: string) => /[a-z]/.test(p) },
  { key: 'number',  label: 'One number (0–9)',              test: (p: string) => /[0-9]/.test(p) },
  { key: 'special', label: 'One special character (!@#…)', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
] as const

export const passwordOk = (p: string) => PWD_RULES.every(r => r.test(p))

export function RuleLine({ pass, label }: { pass: boolean; label: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full shrink-0 ${pass ? 'bg-[#C800DE]' : 'bg-red-500'}`}>
        {pass ? (
          <svg width="7" height="6" viewBox="0 0 7 6" fill="none">
            <path d="M1 3L2.8 5L6 1" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        ) : (
          <svg width="7" height="7" viewBox="0 0 7 7" fill="none">
            <path d="M1.5 1.5L5.5 5.5M5.5 1.5L1.5 5.5" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
        )}
      </span>
      <span className={`text-[11px] ${pass ? 'text-[#C800DE]' : 'text-red-500'}`}>{label}</span>
    </li>
  )
}

/** The rules, ticking as `password` is typed (hidden until something is typed). */
export function PasswordChecklist({ password }: { password: string }) {
  if (!password) return null
  return <ul className="flex flex-col gap-1 mt-1">{PWD_RULES.map(r => <RuleLine key={r.key} pass={r.test(password)} label={r.label} />)}</ul>
}

/** "Passwords match / do not match" under the confirm field (hidden until something is typed). */
export function PasswordMatch({ password, confirm }: { password: string; confirm: string }) {
  if (!confirm) return null
  const same = password === confirm
  return <ul className="mt-1"><RuleLine pass={same} label={same ? 'Passwords match' : 'Passwords do not match'} /></ul>
}
