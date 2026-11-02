/**
 * FOID-branded date picker (used for date of birth).
 *
 * - Brand purple selection, FOID wordmark in the panel header
 * - Month + year selects for fast jumps (DOB can be decades back)
 * - Dates outside [min, max] are disabled (default max: today)
 * - Phones (< sm): bottom sheet with large tap targets; sm+: popover under the field
 * - Esc / backdrop / Done close it; value is 'YYYY-MM-DD' or ''
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'

const BRAND = '#C800DE'
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December']
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

function pad(n: number) { return String(n).padStart(2, '0') }
function toIso(y: number, m: number, d: number) { return `${y}-${pad(m + 1)}-${pad(d)}` }
function todayIso() { const t = new Date(); return toIso(t.getFullYear(), t.getMonth(), t.getDate()) }
function parseIso(v: string): { y: number; m: number; d: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v)
  return match ? { y: +match[1], m: +match[2] - 1, d: +match[3] } : null
}
function formatLong(v: string) {
  const p = parseIso(v)
  return p ? `${p.d} ${MONTHS[p.m]} ${p.y}` : ''
}

export default function DatePicker({
  value,
  onChange,
  min = '1900-01-01',
  max = todayIso(),
  placeholder = 'Select date',
  disabled = false,
  id,
}: {
  value: string
  onChange: (value: string) => void
  min?: string
  max?: string
  placeholder?: string
  disabled?: boolean
  id?: string
}) {
  const [open, setOpen] = useState(false)
  const initial = parseIso(value) ?? parseIso(max) ?? { y: 1995, m: 0, d: 1 }
  const [viewY, setViewY] = useState(initial.y)
  const [viewM, setViewM] = useState(initial.m)
  const wrapRef = useRef<HTMLDivElement>(null)

  const minP = parseIso(min)!
  const maxP = parseIso(max)!

  // Re-centre the calendar on the current value whenever it opens.
  useEffect(() => {
    if (!open) return
    const p = parseIso(value) ?? parseIso(max)
    if (p) { setViewY(p.y); setViewM(p.m) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  const years = useMemo(() => {
    const out: number[] = []
    for (let y = maxP.y; y >= minP.y; y--) out.push(y)
    return out
  }, [minP.y, maxP.y])

  const cells = useMemo(() => {
    const first = new Date(viewY, viewM, 1).getDay()
    const days = new Date(viewY, viewM + 1, 0).getDate()
    const out: (number | null)[] = Array.from({ length: first }, () => null)
    for (let d = 1; d <= days; d++) out.push(d)
    while (out.length % 7) out.push(null)
    return out
  }, [viewY, viewM])

  const inRange = (iso: string) => iso >= min && iso <= max
  const canPrev = toIso(viewY, viewM, 1) > min.slice(0, 8) + '01'
  const canNext = toIso(viewY, viewM, 1) < max.slice(0, 8) + '01'

  function shiftMonth(delta: number) {
    const d = new Date(viewY, viewM + delta, 1)
    setViewY(d.getFullYear())
    setViewM(d.getMonth())
  }

  const today = todayIso()

  const panel = (
    <div
      role="dialog"
      aria-label="Choose a date"
      className={[
        'bg-white z-50 flex flex-col',
        // phones: bottom sheet
        'fixed inset-x-0 bottom-0 rounded-t-2xl p-4 pb-6 shadow-[0_-10px_40px_rgba(0,0,0,0.18)]',
        // sm+: popover anchored under the field
        'sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:top-full sm:mt-2 sm:w-[320px] sm:rounded-2xl sm:p-4 sm:shadow-xl sm:border sm:border-neutral-100',
      ].join(' ')}
    >
      {/* Branded header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FoidWordmark height={12} color={BRAND} />
          <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">Date of birth</span>
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={() => setOpen(false)}
          className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-neutral-100"
        >
          <RemixIcon name="ri-close-line" size={18} color="#71717a" />
        </button>
      </div>

      {/* Month / year navigation */}
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          aria-label="Previous month"
          disabled={!canPrev}
          onClick={() => shiftMonth(-1)}
          className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-[#fae8ff] disabled:opacity-30"
        >
          <RemixIcon name="ri-arrow-left-s-line" size={20} color={BRAND} />
        </button>
        <select
          aria-label="Month"
          value={viewM}
          onChange={e => setViewM(+e.target.value)}
          className="flex-1 min-w-0 rounded-lg border border-neutral-200 px-2 py-2 text-[13px] font-semibold text-neutral-900 bg-white outline-none focus:border-[#C800DE]"
        >
          {MONTHS.map((m, i) => <option key={m} value={i}>{m}</option>)}
        </select>
        <select
          aria-label="Year"
          value={viewY}
          onChange={e => setViewY(+e.target.value)}
          className="w-[92px] rounded-lg border border-neutral-200 px-2 py-2 text-[13px] font-semibold text-neutral-900 bg-white outline-none focus:border-[#C800DE]"
        >
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>
        <button
          type="button"
          aria-label="Next month"
          disabled={!canNext}
          onClick={() => shiftMonth(1)}
          className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-[#fae8ff] disabled:opacity-30"
        >
          <RemixIcon name="ri-arrow-right-s-line" size={20} color={BRAND} />
        </button>
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-1 text-center">
        {WEEKDAYS.map(w => (
          <div key={w} className="text-[11px] font-semibold text-neutral-400 py-1">{w}</div>
        ))}
        {cells.map((d, i) => {
          if (d === null) return <div key={`e${i}`} />
          const iso = toIso(viewY, viewM, d)
          const selected = iso === value
          const enabled = inRange(iso)
          return (
            <button
              key={iso}
              type="button"
              disabled={!enabled}
              onClick={() => { onChange(iso); setOpen(false) }}
              aria-label={formatLong(iso)}
              aria-pressed={selected}
              className={[
                'mx-auto w-10 h-10 sm:w-9 sm:h-9 rounded-full text-[13px] font-medium transition-colors',
                selected ? 'text-white' : enabled ? 'text-neutral-800 hover:bg-[#fae8ff]' : 'text-neutral-300 cursor-not-allowed',
                !selected && iso === today ? 'ring-1 ring-[#C800DE]' : '',
              ].join(' ')}
              style={selected ? { background: BRAND } : undefined}
            >
              {d}
            </button>
          )
        })}
      </div>

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-neutral-100">
        <span className="text-[12px] text-neutral-500 truncate">{value ? formatLong(value) : 'No date selected'}</span>
        <div className="flex gap-2 shrink-0">
          {value && (
            <button type="button" onClick={() => onChange('')}
              className="px-3 py-1.5 rounded-full text-[12px] font-semibold text-neutral-600 hover:bg-neutral-100">
              Clear
            </button>
          )}
          <button type="button" onClick={() => setOpen(false)}
            className="px-4 py-1.5 rounded-full text-[12px] font-bold text-white hover:opacity-90"
            style={{ background: BRAND }}>
            Done
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div ref={wrapRef} className="relative">
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-2 border border-neutral-200 rounded-lg px-3 py-2 text-[14px] bg-white outline-none focus:ring-2 focus:ring-[#C800DE]/30 focus:border-[#C800DE] disabled:bg-neutral-50 disabled:text-neutral-400"
      >
        <span className={value ? 'text-neutral-900' : 'text-neutral-400'}>{value ? formatLong(value) : placeholder}</span>
        <RemixIcon name="ri-calendar-line" size={17} color={BRAND} />
      </button>
      {open && (
        <>
          {/* phone backdrop */}
          <div className="fixed inset-0 z-40 bg-black/30 sm:hidden" onClick={() => setOpen(false)} />
          {panel}
        </>
      )}
    </div>
  )
}
