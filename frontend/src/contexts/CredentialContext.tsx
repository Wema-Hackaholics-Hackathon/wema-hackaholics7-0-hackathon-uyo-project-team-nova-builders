/**
 * CredentialContext — the core FOID artifact.
 *
 * Manages a single FoidCredential whose `state` moves through:
 *   active → under_review → downgraded → revoked
 *
 * State transitions are triggered by deterministic, rule-based events
 * injected via the Demo Control Panel (or simulated Open Banking events).
 * NO ML, NO credit scoring. This is a credential state machine.
 *
 * Every transition emits a Notification (what changed, why, what to do).
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react'
import type { CredentialState, FoidCredential, Notification } from '../types/foid'
import { api } from '../lib/api'

/* ── Fallback credential used only while the backend fetch is in-flight ── */
const EMPTY_CREDENTIAL: FoidCredential = {
  id: '',
  holder: '',
  state: 'active',
  claims: {
    identity_verified: false,
    bvn_validated: false,
    age_over_18: false,
    income_band: 'low',
    account_stability: 'poor',
    repayment_reliability: 'poor',
  },
  issued_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

/* ── Trigger event definitions ──────────────────────────────────────── */
export type TriggerEvent =
  | 'missed_repayment'      // active → under_review
  | 'suspicious_activity'   // active → under_review
  | 'income_drop'           // under_review → downgraded
  | 'manual_revoke'         // * → revoked
  | 'review_cleared'        // under_review → active
  | 'appeal_approved'       // downgraded → active
  | 'repayment_restored'    // downgraded → under_review

export interface TriggerEventMeta {
  event: TriggerEvent
  label: string
  description: string
  /** The state the credential must currently be in to allow this trigger (null = any) */
  requiredState: CredentialState | null
  /** Resulting state after the transition */
  resultState: CredentialState
  /** Human-readable reason shown in the notification */
  reason: string
  action: string
}

export const TRIGGER_EVENTS: TriggerEventMeta[] = [
  {
    event: 'missed_repayment',
    label: 'Missed repayment',
    description: 'Simulate a missed loan repayment detected via Open Banking feed',
    requiredState: 'active',
    resultState: 'under_review',
    reason: 'A missed repayment was detected on your connected bank account.',
    action: 'Review your linked accounts and resolve any outstanding payments.',
  },
  {
    event: 'suspicious_activity',
    label: 'Suspicious activity',
    description: 'Simulate an unusual transaction pattern flagged by rules engine',
    requiredState: 'active',
    resultState: 'under_review',
    reason: 'Unusual transaction patterns were detected on your account.',
    action: 'Verify your recent transactions and contact support if needed.',
  },
  {
    event: 'income_drop',
    label: 'Significant income drop',
    description: 'Simulate >40% income drop over 2 consecutive months',
    requiredState: 'under_review',
    resultState: 'downgraded',
    reason: 'A significant income drop (>40%) was detected over two consecutive months.',
    action: 'Upload recent proof of income or link an additional account.',
  },
  {
    event: 'review_cleared',
    label: 'Review cleared',
    description: 'Simulate passing the review (repayment resolved, no issues found)',
    requiredState: 'under_review',
    resultState: 'active',
    reason: 'Your account review has been completed with no outstanding issues.',
    action: 'No action required — your credential is fully active again.',
  },
  {
    event: 'repayment_restored',
    label: 'Repayment restored',
    description: 'Simulate repayment resumed after a downgrade',
    requiredState: 'downgraded',
    resultState: 'under_review',
    reason: 'Repayment activity has resumed. Your credential is back under review.',
    action: 'Continue maintaining regular repayments to restore full status.',
  },
  {
    event: 'appeal_approved',
    label: 'Appeal approved',
    description: 'Simulate a successful appeal reinstating a downgraded credential',
    requiredState: 'downgraded',
    resultState: 'active',
    reason: 'Your appeal has been reviewed and approved.',
    action: 'No action required — your credential is fully active again.',
  },
  {
    event: 'manual_revoke',
    label: 'Manual revoke',
    description: 'Permanently revoke the credential (irreversible in demo)',
    requiredState: null,
    resultState: 'revoked',
    reason: 'Your FOID credential has been manually revoked.',
    action: 'Contact support or re-verify your identity to issue a new credential.',
  },
]

/* ── State transition descriptions ─────────────────────────────────── */
const STATE_CHANGE_LABEL: Record<CredentialState, string> = {
  active: 'Credential restored to Active',
  under_review: 'Credential placed Under Review',
  downgraded: 'Credential Downgraded',
  revoked: 'Credential Revoked',
}

/* ── Context shape ──────────────────────────────────────────────────── */
interface CredentialContextValue {
  credential: FoidCredential
  loading: boolean
  notifications: Notification[]
  unreadCount: number
  triggerEvent: (event: TriggerEvent) => void
  markAllRead: () => void
  markRead: (id: string) => void
}

const CredentialContext = createContext<CredentialContextValue | null>(null)

/* ── Provider ───────────────────────────────────────────────────────── */
export function CredentialProvider({ children }: { children: ReactNode }) {
  const [credential, setCredential] = useState<FoidCredential>(EMPTY_CREDENTIAL)
  const [loading, setLoading] = useState(true)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const notifIdRef = useRef(0)

  // ── Fetch real credential from backend on mount ──────────────────────
  useEffect(() => {
    api.get<FoidCredential>('/credentials/me')
      .then(r => setCredential(r.data))
      .catch(() => { /* leave EMPTY_CREDENTIAL in place — not yet issued */ })
      .finally(() => setLoading(false))
  }, [])

  const triggerEvent = useCallback((event: TriggerEvent) => {
    const meta = TRIGGER_EVENTS.find(e => e.event === event)
    if (!meta) return

    setCredential(prev => {
      // Guard: only allow if the required state matches (or null = any)
      if (meta.requiredState !== null && prev.state !== meta.requiredState) return prev

      const next: FoidCredential = {
        ...prev,
        state: meta.resultState,
        updated_at: new Date().toISOString(),
        // Update claims based on resulting state
        claims: {
          ...prev.claims,
          account_stability:
            meta.resultState === 'active' ? 'stable' :
            meta.resultState === 'under_review' ? 'variable' : 'poor',
          repayment_reliability:
            meta.resultState === 'active' ? 'reliable' :
            meta.resultState === 'under_review' ? 'variable' : 'poor',
          income_band:
            meta.resultState === 'downgraded' ? 'low' :
            meta.resultState === 'active' ? 'high' : prev.claims.income_band,
        },
      }

      // Emit notification
      const notif: Notification = {
        id: `notif_${++notifIdRef.current}`,
        message: STATE_CHANGE_LABEL[meta.resultState],
        change: `${prev.state} → ${meta.resultState}`,
        reason: meta.reason,
        action: meta.action,
        timestamp: new Date().toISOString(),
        read: false,
      }
      setNotifications(ns => [notif, ...ns])

      return next
    })
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications(ns => ns.map(n => ({ ...n, read: true })))
  }, [])

  const markRead = useCallback((id: string) => {
    setNotifications(ns => ns.map(n => n.id === id ? { ...n, read: true } : n))
  }, [])

  const unreadCount = notifications.filter(n => !n.read).length

  return (
    <CredentialContext.Provider value={{ credential, loading, notifications, unreadCount, triggerEvent, markAllRead, markRead }}>
      {children}
    </CredentialContext.Provider>
  )
}

/* ── Hook ───────────────────────────────────────────────────────────── */
export function useCredential() {
  const ctx = useContext(CredentialContext)
  if (!ctx) throw new Error('useCredential must be used inside <CredentialProvider>')
  return ctx
}
