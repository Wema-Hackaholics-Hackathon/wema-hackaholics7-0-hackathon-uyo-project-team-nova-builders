/** Top-bar bell: this member's notifications for the current business (checks every 45 s). */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'
import { useMode } from '@/contexts/ModeContext'
import { api } from '@/lib/api'
import { ago, useFetch } from '@/lib/useFetch'

interface Item { id: string; kind: string; title: string; body: string; link: string | null; read: boolean; created_at: string }

const ICON: Record<string, string> = {
  kyb_approved: 'ri-checkbox-circle-line', kyb_rejected: 'ri-error-warning-line', invoice_paid: 'ri-bank-card-line',
  invoice_due: 'ri-file-list-3-line', webhook_failing: 'ri-webhook-line', api_key_created: 'ri-key-2-line',
  api_keys_revoked: 'ri-key-2-line', member_joined: 'ri-user-add-line', consent_revoked: 'ri-shield-user-line',
  org_deactivated: 'ri-pause-circle-line', org_reactivated: 'ri-play-circle-line',
}

export default function NotificationBell() {
  const { org } = useMode()
  const navigate = useNavigate()
  const base = org ? `/business/organisations/${org.id}/notifications` : null
  const { data, reload } = useFetch<{ data: Item[]; unread: number }>(base)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!base) return
    const t = setInterval(() => { if (document.visibilityState === 'visible') void reload() }, 45_000)
    return () => clearInterval(t)
  }, [base, reload])
  useEffect(() => {
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const unread = data?.unread ?? 0
  const openItem = async (n: Item) => {
    setOpen(false)
    if (!n.read) await api.post(`${base}/${n.id}/read`).catch(() => {})
    void reload()
    if (n.link) navigate(n.link)
  }
  const readAll = async () => { await api.post(`${base}/read-all`).catch(() => {}); void reload() }

  return (
    <div ref={box} className="relative">
      <button aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'} aria-expanded={open}
        onClick={() => { setOpen(o => !o); if (!open) void reload() }}
        className="w-10 h-10 rounded-full p-3 bg-neutral-100 flex items-center justify-center hover:bg-neutral-200 transition-colors">
        <div className="relative">
          <RemixIcon name="ri-notification-3-fill" size={16} color="#000000" clickable />
          {unread > 0 && <span className="absolute top-1 right-0 w-2 h-2 rounded-full bg-brand-400 border-2 border-white" />}
        </div>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 z-50 w-[340px] max-w-[calc(100vw-24px)] bg-white rounded-xl shadow-lg border border-neutral-200 font-normal">
          <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-100">
            <span className="text-[14px] font-bold">Notifications{unread ? ` · ${unread} new` : ''}</span>
            {unread > 0 && <button onClick={() => void readAll()} className="text-[12px] font-semibold text-[#c026d3]">Mark all as read</button>}
          </div>
          <div className="max-h-[400px] overflow-y-auto">
            {data?.data.map(n => (
              <button key={n.id} onClick={() => void openItem(n)}
                className={`w-full flex gap-3 px-4 py-3 text-left border-b border-neutral-100 last:border-0 hover:bg-neutral-50 ${n.read ? '' : 'bg-brand-50/60'}`}>
                <RemixIcon name={ICON[n.kind] ?? 'ri-information-line'} size={18} color={n.read ? '#a1a1aa' : '#c026d3'} />
                <span className="flex-1 min-w-0">
                  <span className={`block text-[13px] ${n.read ? 'text-neutral-700' : 'font-semibold text-neutral-900'}`}>{n.title}</span>
                  {n.body && <span className="block text-[12px] text-neutral-500 line-clamp-2">{n.body}</span>}
                  <span className="block text-[11px] text-neutral-400 mt-0.5">{ago(n.created_at)}</span>
                </span>
                {!n.read && <span className="mt-1.5 w-2 h-2 rounded-full bg-[#c026d3] shrink-0" />}
              </button>
            ))}
            {data && !data.data.length && <p className="px-4 py-8 text-center text-[13px] text-neutral-400">You’re all caught up.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
