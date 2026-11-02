/**
 * Current organisation + Test (sandbox) / Live.
 *  - orgs come from GET /business/organisations (each with the member's role and KYB status);
 *  - the chosen org and its mode are remembered in localStorage;
 *  - Test is the default; Live stays locked until FOID approves the documents (kyb_status=approved).
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '@/lib/api'
import { useAuth } from './AuthContext'

export type Mode = 'test' | 'live'
export type KybStatus = 'not_submitted' | 'pending' | 'approved' | 'rejected'
export type Role = 'owner' | 'admin' | 'developer' | 'reviewer' | 'viewer'

export interface Org {
  id: string
  name: string
  support_email: string | null
  kyb_status: KybStatus
  live_enabled: boolean
  role: Role
  plan: string
  status: 'active' | 'suspended'
  require_2fa: boolean
  deactivated_at: string | null
}

const RANK: Record<Role, number> = { viewer: 0, reviewer: 1, developer: 2, admin: 3, owner: 4 }
const ORG_KEY = 'foid_console_org'
const modeKey = (orgId: string) => `foid_console_mode:${orgId}`

interface OrgState {
  orgs: Org[]
  org: Org | null
  selectOrg: (id: string) => void
  reloadOrgs: () => Promise<void>
  /** true if the member's role in the current org is at least `min` */
  can: (min: Role) => boolean
  mode: Mode
  setMode: (m: Mode) => void
  kyb: KybStatus
  liveUnlocked: boolean
}

const Ctx = createContext<OrgState | null>(null)

export function ModeProvider({ children }: { children: ReactNode }) {
  const { member } = useAuth()
  const [orgs, setOrgs] = useState<Org[]>([])
  const [orgId, setOrgId] = useState<string | null>(() => localStorage.getItem(ORG_KEY))
  const [wanted, setWanted] = useState<Mode>('test')

  const reloadOrgs = useCallback(async () => {
    setOrgs((await api.get<Org[]>('/business/organisations')).data)
  }, [])

  useEffect(() => {
    if (member?.email_verified) void reloadOrgs()
    else setOrgs([])
  }, [member, reloadOrgs])

  const org = orgs.find(o => o.id === orgId) ?? orgs[0] ?? null

  useEffect(() => {   // restore this org's last mode
    if (org) setWanted((localStorage.getItem(modeKey(org.id)) as Mode) || 'test')
  }, [org?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const kyb = org?.kyb_status ?? 'not_submitted'
  const liveUnlocked = kyb === 'approved'
  const mode: Mode = wanted === 'live' && liveUnlocked ? 'live' : 'test'   // Live never shows while locked

  const value: OrgState = {
    orgs, org, reloadOrgs,
    selectOrg: id => { localStorage.setItem(ORG_KEY, id); setOrgId(id) },
    can: min => !!org && RANK[org.role] >= RANK[min],
    mode,
    setMode: m => { if (org) localStorage.setItem(modeKey(org.id), m); setWanted(m) },
    kyb, liveUnlocked,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useMode() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useMode outside ModeProvider')
  return c
}
