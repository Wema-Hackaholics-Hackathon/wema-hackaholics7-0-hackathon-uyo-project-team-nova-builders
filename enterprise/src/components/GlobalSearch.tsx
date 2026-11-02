/** Top-bar search: people (name, email, FOID code, your ref) and request IDs (req_…). */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'
import { useMode } from '@/contexts/ModeContext'
import { api } from '@/lib/api'

interface Results {
  users: { id: string; code: string; name: string | null; email: string | null; status: string }[]
  requests: { request_id: string; method: string; path: string; status: number }[]
}

export default function GlobalSearch() {
  const { org, mode } = useMode()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<Results | null>(null)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const term = q.trim()
    if (!org || term.length < 2) { setRes(null); return }
    const t = setTimeout(() => {
      api.get<Results>(`/business/organisations/${org.id}/search`, { params: { q: term, env: mode } })
        .then(r => setRes(r.data)).catch(() => setRes(null))
    }, 250)
    return () => clearTimeout(t)
  }, [q, org, mode])

  useEffect(() => {
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const go = (path: string) => { setOpen(false); setQ(''); navigate(path) }
  const empty = res && !res.users.length && !res.requests.length

  return (
    <div ref={box} className="relative flex-1 max-w-[500px] hidden md:flex justify-center py-2">
      <RemixIcon name="ri-search-fill" size={20} color="#a1a1aa" className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        type="text" value={q} onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true) }}
        onKeyDown={e => { if (e.key === 'Escape') setOpen(false); if (e.key === 'Enter' && q.trim()) go(q.trim().startsWith('req_') ? `/logs?q=${encodeURIComponent(q.trim())}` : `/users?q=${encodeURIComponent(q.trim())}`) }}
        placeholder="Search your users, FOID code, request ID" aria-label="Search"
        className="w-full pl-11 pr-4 py-2 rounded-full bg-neutral-100 text-neutral-800 placeholder:text-neutral-400 focus:outline-none focus:border-brand-400"
      />
      {open && res && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white rounded-xl shadow-lg border border-neutral-200 py-2 text-[13px] font-normal">
          {res.users.map(u => (
            <button key={u.id} onClick={() => go(`/users?q=${encodeURIComponent(u.code)}`)} className="w-full flex items-center gap-3 px-4 py-2 hover:bg-neutral-50 text-left">
              <RemixIcon name="ri-user-line" size={16} color="#a1a1aa" />
              <span className="flex-1 min-w-0 truncate"><b>{u.name ?? 'Hidden by consent'}</b> <span className="text-neutral-400">{u.email ?? ''}</span></span>
              <span className="font-mono text-[11.5px] text-neutral-500">{u.code}</span>
            </button>
          ))}
          {res.requests.map(r => (
            <button key={r.request_id} onClick={() => go(`/logs?q=${encodeURIComponent(r.request_id)}`)} className="w-full flex items-center gap-3 px-4 py-2 hover:bg-neutral-50 text-left">
              <RemixIcon name="ri-terminal-box-line" size={16} color="#a1a1aa" />
              <span className="flex-1 min-w-0 truncate font-mono text-[12px]">{r.method} {r.path}</span>
              <span className="text-[11.5px] text-neutral-500">{r.status}</span>
            </button>
          ))}
          {empty && <p className="px-4 py-2 text-neutral-400">No matches in {mode}. Request IDs start with req_.</p>}
        </div>
      )}
    </div>
  )
}
