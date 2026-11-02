/** Top-bar bell for the signed-in FOID user (GET /notifications; checks every 60 s). */
import { useCallback, useEffect, useRef, useState } from 'react'
import RemixIcon from './RemixIcon'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

interface Item { id: string; message: string; change: string; reason: string; action: string; timestamp: string; read: boolean }

function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} hr${s >= 7200 ? 's' : ''} ago`
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export default function NotificationBell() {
  const { user } = useAuth()
  const [items, setItems] = useState<Item[]>([])
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    if (!user) return
    try { setItems((await api.get<Item[]>('/notifications', { params: { limit: 10 } })).data) } catch { /* keep the last list */ }
  }, [user])

  useEffect(() => {
    void load()
    const t = setInterval(() => { if (document.visibilityState === 'visible') void load() }, 60_000)
    return () => clearInterval(t)
  }, [load])
  useEffect(() => {
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const unread = items.filter(n => !n.read).length
  const markRead = async (n: Item) => {
    if (n.read) return
    setItems(list => list.map(x => x.id === n.id ? { ...x, read: true } : x))
    await api.patch(`/notifications/${n.id}/read`).catch(() => {})
  }
  const readAll = async () => {
    setItems(list => list.map(x => ({ ...x, read: true })))
    await api.patch('/notifications/read-all').catch(() => {})
  }

  return (
    <div ref={box} className="relative">
      <button aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'} aria-expanded={open}
        onClick={() => { setOpen(o => !o); if (!open) void load() }}
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
            {unread > 0 && <button onClick={() => void readAll()} className="text-[12px] font-semibold text-brand-500">Mark all as read</button>}
          </div>
          <div className="max-h-[400px] overflow-y-auto">
            {items.map(n => (
              <button key={n.id} onClick={() => void markRead(n)}
                className={`w-full flex gap-3 px-4 py-3 text-left border-b border-neutral-100 last:border-0 hover:bg-neutral-50 ${n.read ? '' : 'bg-brand-50/60'}`}>
                <RemixIcon name="ri-shield-check-line" size={18} color={n.read ? '#a1a1aa' : '#c026d3'} />
                <span className="flex-1 min-w-0">
                  <span className={`block text-[13px] ${n.read ? 'text-neutral-700' : 'font-semibold text-neutral-900'}`}>{n.message}</span>
                  <span className="block text-[12px] text-neutral-500 line-clamp-2">{n.reason}</span>
                  {n.action && <span className="block text-[12px] text-neutral-500 line-clamp-2">{n.action}</span>}
                  <span className="block text-[11px] text-neutral-400 mt-0.5">{ago(n.timestamp)}</span>
                </span>
                {!n.read && <span className="mt-1.5 w-2 h-2 rounded-full bg-brand-500 shrink-0" />}
              </button>
            ))}
            {!items.length && <p className="px-4 py-8 text-center text-[13px] text-neutral-400">You’re all caught up.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
