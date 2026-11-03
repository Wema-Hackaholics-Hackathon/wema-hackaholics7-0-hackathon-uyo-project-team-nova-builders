/**
 * Top-bar search box + results dropdown. The parent supplies the (already filtered) results;
 * this handles focus ("/" or Ctrl/⌘+K), arrow keys, Enter, Esc and click-away.
 * Same file in frontend/ and enterprise/.
 */
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'

export interface SearchItem {
  key: string
  group: string
  icon: string
  title: string
  sub?: string
  meta?: string
  to: string
}

interface Props {
  placeholder: string
  query: string
  onQuery: (q: string) => void
  items: SearchItem[]
  /** shown under the results, e.g. "Searching…" or "No matches" */
  note?: string
  /** called the first time the box opens, so data loads only when someone searches */
  onOpen?: () => void
}

/** Case-insensitive "every word appears somewhere" match. */
export function matches(q: string, ...fields: (string | null | undefined)[]): boolean {
  const hay = fields.filter(Boolean).join(' ').toLowerCase()
  return q.toLowerCase().split(/\s+/).filter(Boolean).every(w => hay.includes(w))
}

export default function SearchBox({ placeholder, query, onQuery, items, note, onOpen }: Props) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => setActive(0), [query])
  useEffect(() => { if (open) onOpen?.() }, [open, onOpen])

  useEffect(() => {
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const shortcut = (e: globalThis.KeyboardEvent) => {
      const el = e.target as HTMLElement
      const typing = el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)
      if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        input.current?.focus()
        input.current?.select()
      }
    }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', shortcut)
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', shortcut) }
  }, [])

  const go = (item: SearchItem | undefined) => {
    if (!item) return
    setOpen(false)
    onQuery('')
    input.current?.blur()
    navigate(item.to)
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(i => Math.min(i + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(i => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[active]) }
  }

  let lastGroup = ''
  return (
    <div ref={box} className="relative flex-1 max-w-[500px] hidden md:flex justify-center py-2">
      <RemixIcon name="ri-search-fill" size={20} color="#a1a1aa" className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        ref={input}
        type="text"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={e => { onQuery(e.target.value); setOpen(true) }}
        onKeyDown={onKey}
        placeholder={placeholder}
        aria-label="Search"
        role="combobox"
        aria-expanded={open}
        className="w-full pl-11 pr-12 py-2 rounded-full bg-neutral-100 text-neutral-800 placeholder:text-neutral-400 focus:outline-none focus:border-brand-400"
      />
      {!open && (
        <kbd className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-[11px] font-semibold text-neutral-400 border border-neutral-200 rounded px-1.5">/</kbd>
      )}
      {open && (items.length > 0 || note) && (
        <div role="listbox" className="absolute z-50 top-full left-0 right-0 mt-1 bg-white rounded-xl shadow-lg border border-neutral-200 py-2 text-[13px] font-normal max-h-[420px] overflow-y-auto">
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? it.group : ''
            lastGroup = it.group
            return (
              <div key={it.key}>
                {header && <div className="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-neutral-400">{header}</div>}
                <button
                  role="option"
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(it)}
                  className={`w-full flex items-center gap-3 px-4 py-2 text-left ${i === active ? 'bg-neutral-100' : ''}`}
                >
                  <RemixIcon name={it.icon} size={16} color="#a1a1aa" />
                  <span className="flex-1 min-w-0 truncate">
                    <b className="font-semibold text-neutral-900">{it.title}</b>
                    {it.sub && <span className="text-neutral-400"> {it.sub}</span>}
                  </span>
                  {it.meta && <span className="shrink-0 text-[11.5px] text-neutral-500">{it.meta}</span>}
                </button>
              </div>
            )
          })}
          {note && <p className="px-4 py-2 text-neutral-400">{note}</p>}
        </div>
      )}
    </div>
  )
}
