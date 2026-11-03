/**
 * Top-bar search over the signed-in user's own data: pages, connected banks, recent
 * transactions, businesses with access and notifications. Everything is fetched once
 * when the box is first opened (again after 2 min) and filtered in the browser.
 */
import { useCallback, useMemo, useRef, useState } from 'react'
import SearchBox, { matches, type SearchItem } from './SearchBox'
import { api } from '@/lib/api'
import type { ConnectedApp, ConnectedBank, MonoTransaction } from '@/types/foid'

const PAGES: { to: string; icon: string; title: string; keywords: string }[] = [
  { to: '/dashboard', icon: 'ri-dashboard-fill', title: 'Overview', keywords: 'home dashboard summary foid code qr' },
  { to: '/dashboard/identity', icon: 'ri-fingerprint-line', title: 'My Identity', keywords: 'nin bvn liveness face selfie phone verify kyc identity summary' },
  { to: '/dashboard/banks', icon: 'ri-bank-line', title: 'Connected Banks', keywords: 'bank account mono link connect sync' },
  { to: '/dashboard/credentials', icon: 'ri-draft-line', title: 'Verification Credentials', keywords: 'credential shared claims revoke' },
  { to: '/dashboard/consents', icon: 'ri-file-list-3-line', title: 'Consent Requests', keywords: 'consent business access connected apps revoke permission' },
  { to: '/dashboard/ledger', icon: 'ri-store-2-fill', title: 'Business Ledger', keywords: 'ledger record sale income expense cash' },
  { to: '/dashboard/history', icon: 'ri-history-fill', title: 'Ledger History', keywords: 'ledger history entries' },
  { to: '/dashboard/wallet', icon: 'ri-quill-pen-line', title: 'AI Credit Wallet', keywords: 'ai chat assistant credits buy top up wallet' },
  { to: '/dashboard/reports', icon: 'ri-customer-service-2-fill', title: 'Reports & Insights', keywords: 'report tax pdf csv export statement insights' },
  { to: '/dashboard/settings', icon: 'ri-settings-3-line', title: 'Profile & Settings', keywords: 'profile password two-factor 2fa security login alerts address avatar notifications' },
]

interface Notif { id: string; message: string; reason: string; timestamp: string }
interface Data { banks: ConnectedBank[]; tx: (MonoTransaction & { bankId: string; bankName: string })[]; apps: ConnectedApp[]; notes: Notif[] }

const naira = (kobo: number) => '₦' + (kobo / 100).toLocaleString('en-NG', { maximumFractionDigits: 0 })
const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
const qs = (s: string) => `?q=${encodeURIComponent(s)}`

/** Where a notification is best dealt with. */
function notifTarget(n: Notif): string {
  const t = `${n.message} ${n.reason}`.toLowerCase()
  if (/business|connected app|consent|shar/.test(t)) return '/dashboard/consents'
  if (/bvn|nin|liveness|face|identity/.test(t)) return '/dashboard/identity'
  return '/dashboard/credentials'
}

export default function GlobalSearch() {
  const [q, setQ] = useState('')
  const [data, setData] = useState<Data | null>(null)
  const [loading, setLoading] = useState(false)
  const loadedAt = useRef(0)

  const load = useCallback(() => {
    if (Date.now() - loadedAt.current < 120_000) return
    loadedAt.current = Date.now()
    setLoading(true)
    void (async () => {
      const [banks, apps, notes] = await Promise.allSettled([
        api.get<ConnectedBank[]>('/banks/connected'),
        api.get<ConnectedApp[]>('/connected-apps'),
        api.get<Notif[]>('/notifications', { params: { limit: 50 } }),
      ])
      const bankList = banks.status === 'fulfilled' ? banks.value.data : []
      const txs = await Promise.allSettled(bankList.map(b =>
        api.get<MonoTransaction[]>(`/banks/${b.id}/transactions`, { params: { limit: 100 } })
          .then(r => r.data.map(t => ({ ...t, bankId: b.id, bankName: b.name })))))
      setData({
        banks: bankList,
        tx: txs.flatMap(r => (r.status === 'fulfilled' ? r.value : [])),
        apps: apps.status === 'fulfilled' ? apps.value.data : [],
        notes: notes.status === 'fulfilled' ? notes.value.data : [],
      })
      setLoading(false)
    })()
  }, [])

  const items = useMemo<SearchItem[]>(() => {
    const term = q.trim()
    const pages = PAGES.filter(p => !term || matches(term, p.title, p.keywords))
      .map(p => ({ key: p.to, group: 'Pages', icon: p.icon, title: p.title, to: p.to }))
    if (!term) return pages.slice(0, 6)
    if (!data) return pages
    const out: SearchItem[] = [
      ...pages,
      ...data.banks.filter(b => matches(term, b.name, b.account_type, b.masked_number)).slice(0, 4).map(b => ({
        key: `bank-${b.id}`, group: 'Banks', icon: 'ri-bank-line', title: b.name,
        sub: b.masked_number ?? '', meta: b.status, to: `/dashboard/banks/${b.id}/transactions`,
      })),
      ...data.apps.filter(a => matches(term, a.name, a.website, ...a.scopes.map(s => s.scope))).slice(0, 4).map(a => ({
        key: `app-${a.org_id}-${a.sandbox}`, group: 'Businesses with access', icon: 'ri-building-line',
        title: a.sandbox ? `${a.name} (sandbox)` : a.name, meta: a.status === 'active' ? 'Has access' : 'Revoked',
        to: `/dashboard/consents${qs(a.name)}`,
      })),
      ...(term.length >= 2 ? data.tx.filter(t => matches(term, t.narration, t.category, t.bankName)).slice(0, 6).map(t => ({
        key: `tx-${t.bankId}-${t.id}`, group: 'Transactions', icon: t.type === 'credit' ? 'ri-arrow-down-line' : 'ri-arrow-up-line',
        title: t.narration, sub: `${t.bankName} · ${day(t.date)}`, meta: (t.type === 'credit' ? '+' : '−') + naira(t.amount),
        to: `/dashboard/banks/${t.bankId}/transactions${qs(t.narration)}`,
      })) : []),
      ...(term.length >= 2 ? data.notes.filter(n => matches(term, n.message, n.reason)).slice(0, 4).map(n => ({
        key: `n-${n.id}`, group: 'Notifications', icon: 'ri-notification-3-line', title: n.message,
        meta: day(n.timestamp), to: notifTarget(n),
      })) : []),
    ]
    return out
  }, [q, data])

  const note = !q.trim() ? undefined
    : loading ? 'Searching…'
    : items.length === 0 ? `Nothing matches “${q.trim()}”` : undefined

  return (
    <SearchBox
      placeholder="Search your credentials, banks, transactions"
      query={q} onQuery={setQ} items={items} note={note} onOpen={load}
    />
  )
}
