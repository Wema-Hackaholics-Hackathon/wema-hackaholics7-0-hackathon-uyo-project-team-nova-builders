/**
 * Top-bar search: console pages, people (name, email, FOID code, your ref) and request IDs (req_…).
 * People and requests come from GET /business/organisations/{id}/search in the current mode.
 */
import { useEffect, useMemo, useState } from 'react'
import SearchBox, { matches, type SearchItem } from './SearchBox'
import { useMode } from '@/contexts/ModeContext'
import { api } from '@/lib/api'

interface Results {
  users: { id: string; code: string; name: string | null; email: string | null; status: string }[]
  requests: { request_id: string; method: string; path: string; status: number }[]
}

const PAGES: { to: string; icon: string; title: string; keywords: string }[] = [
  { to: '/', icon: 'ri-dashboard-fill', title: 'Overview', keywords: 'home dashboard stats activity' },
  { to: '/users', icon: 'ri-group-line', title: 'Users', keywords: 'people customers verified subjects consent export' },
  { to: '/api-keys', icon: 'ri-key-2-line', title: 'API keys & webhooks', keywords: 'api key secret webhook rotate revoke developer' },
  { to: '/apps', icon: 'ri-login-circle-line', title: 'Sign-in apps', keywords: 'continue with foid oauth client id secret redirect origin login' },
  { to: '/logs', icon: 'ri-terminal-box-line', title: 'Request logs', keywords: 'logs requests errors 4xx 5xx latency' },
  { to: '/billing', icon: 'ri-bank-card-line', title: 'Billing', keywords: 'plan invoice payment upgrade usage' },
  { to: '/team', icon: 'ri-team-line', title: 'Team', keywords: 'members invite roles admin developer' },
  { to: '/settings', icon: 'ri-settings-3-line', title: 'Settings', keywords: 'organisation profile security ip allowlist 2fa deactivate danger' },
  { to: '/go-live', icon: 'ri-rocket-line', title: 'Go live', keywords: 'kyb documents live mode approval cac' },
  { to: '/account', icon: 'ri-user-settings-line', title: 'My account', keywords: 'profile password two-factor 2fa businesses' },
]

export default function GlobalSearch() {
  const { org, mode } = useMode()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<Results | null>(null)
  const [loading, setLoading] = useState(false)
  const term = q.trim()

  useEffect(() => {
    if (!org || term.length < 2) { setRes(null); setLoading(false); return }
    setLoading(true)
    const t = setTimeout(() => {
      api.get<Results>(`/business/organisations/${org.id}/search`, { params: { q: term, env: mode } })
        .then(r => setRes(r.data)).catch(() => setRes({ users: [], requests: [] }))
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(t)
  }, [term, org, mode])

  const items = useMemo<SearchItem[]>(() => {
    const pages = PAGES.filter(p => !term || matches(term, p.title, p.keywords))
      .map(p => ({ key: p.to, group: 'Pages', icon: p.icon, title: p.title, to: p.to }))
    if (!term) return pages.slice(0, 6)
    return [
      ...pages,
      ...(res?.users ?? []).map(u => ({
        key: `u-${u.id}`, group: `Users (${mode})`, icon: 'ri-user-line', title: u.name ?? 'Hidden by consent',
        sub: u.email ?? '', meta: u.code, to: `/users?q=${encodeURIComponent(u.code)}`,
      })),
      ...(res?.requests ?? []).map(r => ({
        key: `r-${r.request_id}`, group: `Requests (${mode})`, icon: 'ri-terminal-box-line',
        title: `${r.method} ${r.path}`, meta: String(r.status), to: `/logs?q=${encodeURIComponent(r.request_id)}`,
      })),
      // Enter on free text: open the full list filtered by it
      { key: 'all', group: 'More', icon: 'ri-search-line', title: `Search all ${mode} users for “${term}”`,
        to: term.startsWith('req_') ? `/logs?q=${encodeURIComponent(term)}` : `/users?q=${encodeURIComponent(term)}` },
    ]
  }, [term, res, mode])

  const note = term.length === 1 ? 'Keep typing…'
    : loading ? 'Searching…'
    : res && !res.users.length && !res.requests.length ? `No ${mode} users or requests match. Request IDs start with req_.`
    : undefined

  return <SearchBox placeholder="Search your users, FOID code, request ID" query={q} onQuery={setQ} items={items} note={note} />
}
