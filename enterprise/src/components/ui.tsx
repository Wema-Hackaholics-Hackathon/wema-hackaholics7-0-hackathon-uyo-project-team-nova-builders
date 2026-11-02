/** Small building blocks shared by every enterprise page. */
import type { ReactNode } from 'react'
import RemixIcon from './RemixIcon'
import type { Tone } from '@/data/mock'

export const BRAND = '#C800DE'

export function PageHeader({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-8">
      <div>
        <h1 className="text-[28px] md:text-[32px] font-bold text-neutral-900 leading-tight">{title}</h1>
        <p className="text-[15px] text-neutral-500 mt-1">{subtitle}</p>
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </div>
  )
}

export function Button({ icon, children, variant = 'primary', onClick }: {
  icon?: string; children: ReactNode; variant?: 'primary' | 'outline' | 'danger'; onClick?: () => void
}) {
  const cls = {
    primary: 'text-white hover:opacity-90',
    outline: 'border border-neutral-200 text-neutral-900 bg-white hover:bg-neutral-50',
    danger:  'border border-red-300 text-red-600 bg-red-50 hover:bg-red-100',
  }[variant]
  return (
    <button onClick={onClick} style={variant === 'primary' ? { background: BRAND } : undefined}
      className={`inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full text-[14px] font-semibold transition-colors ${cls}`}>
      {icon && <RemixIcon name={icon} size={16} />}
      {children}
    </button>
  )
}

export function Panel({ title, subtitle, action, children, className = '' }: {
  title?: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`bg-white border border-neutral-200 rounded-2xl overflow-hidden ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 px-6 py-5 border-b border-neutral-200">
          <div>
            <h2 className="text-[17px] font-bold text-neutral-900">{title}</h2>
            {subtitle && <p className="text-[12.5px] text-neutral-400 mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

const TONES: Record<Tone, string> = {
  success: 'bg-green-100 text-green-700',
  failed:  'bg-red-100 text-red-600',
  warning: 'bg-orange-100 text-orange-700',
  brand:   'bg-brand-100 text-brand-600',
  neutral: 'bg-neutral-100 text-neutral-600',
}

export function Pill({ tone, children, dot }: { tone: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] font-semibold whitespace-nowrap ${TONES[tone]}`}>
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

/** Plain table: header row + body. Scrolls sideways on small screens. */
export function Table({ cols, children, minWidth = 720 }: { cols: string[]; children: ReactNode; minWidth?: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse" style={{ minWidth }}>
        <thead>
          <tr className="border-b border-neutral-200">
            {cols.map((c, i) => (
              <th key={i} className="px-6 py-4 text-[12px] font-bold text-neutral-500 uppercase tracking-wider whitespace-nowrap">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-neutral-100 [&>tr:last-child]:border-0 [&_td]:px-6 [&_td]:py-4 [&_td]:text-[14px] [&_td]:text-neutral-800">
          {children}
        </tbody>
      </table>
    </div>
  )
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative w-full sm:w-[340px]">
      <RemixIcon name="ri-search-line" size={18} color="#a1a1aa" className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full pl-10 pr-4 py-2.5 rounded-full border border-neutral-200 text-[14px] placeholder:text-neutral-400 focus:outline-none focus:border-brand-400" />
    </div>
  )
}

export function Field({ label, defaultValue, className = '' }: { label: string; defaultValue: string; className?: string }) {
  return (
    <label className={`flex flex-col gap-2 ${className}`}>
      <span className="text-[15px] font-semibold text-neutral-900">{label}</span>
      <input defaultValue={defaultValue}
        className="px-4 py-2.5 rounded-full border border-neutral-300 text-[13.5px] text-neutral-700 focus:outline-none focus:border-brand-400" />
    </label>
  )
}
