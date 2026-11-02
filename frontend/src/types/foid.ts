/** Credential state machine states */
export type CredentialState = 'active' | 'under_review' | 'downgraded' | 'revoked'

/** Core credential claims (v1) */
export interface CredentialClaims {
  identity_verified: boolean
  bvn_validated: boolean
  age_over_18: boolean
  // Admin-verified flags (match backend CredentialClaimsOut)
  nin_verified?: boolean
  phone_verified?: boolean
  bill_verified?: boolean
  email_verified?: boolean
  income_band: 'low' | 'mid' | 'high'
  account_stability: 'stable' | 'variable' | 'poor'
  repayment_reliability: 'reliable' | 'variable' | 'poor'
}

export interface FoidCredential {
  id: string
  holder: string
  state: CredentialState
  claims: CredentialClaims
  issued_at: string
  updated_at: string
}

export interface ConnectedBank {
  id: string
  mono_account_id: string
  name: string
  account_type: string | null
  masked_number: string | null
  status: string
  logo_url: string | null
  last_synced_at: string | null
  created_at: string
}

export interface Notification {
  id: string
  message: string
  change: string
  reason: string
  action: string
  timestamp: string
  read: boolean
}

/** User as returned by GET /auth/me — no password field.
 *  Snake_case fields come from the API; camelCase aliases are
 *  populated by normaliseUser() in AuthContext for UI components. */
export interface User {
  id: string
  // API (snake_case)
  first_name: string
  last_name: string
  middle_name?: string | null
  nin: string
  /** masked, e.g. "*******1234" — the full BVN never leaves the server */
  bvn?: string | null
  /** When the BVN matched the registry under the verified name */
  bvn_verified_at?: string | null
  phone?: string | null
  address?: string | null
  /** Authenticated URL of the enrolled face record (null until enrolled) */
  liveness_selfie_url?: string | null
  /** When a face was last enrolled through a passed liveness check */
  liveness_verified_at?: string | null
  /** Collected during NIN verification (YYYY-MM-DD) */
  date_of_birth?: string | null
  /** When names + DOB matched the NIN record */
  nin_verified_at?: string | null
  /** Names and DOB can't change once the NIN is verified */
  identity_locked?: boolean
  email: string
  created_at: string
  email_verified: boolean
  // camelCase aliases set by AuthContext.normaliseUser()
  firstName: string
  lastName: string
  middleName?: string | null
  createdAt: string
}

export interface ConsentItem {
  id: string
  platform: string
  scope: string
  status: 'pending' | 'approved' | 'revoked'
  logo_url: string | null
  requested_at: string
  expires_at: string | null
}

export interface LedgerEntry {
  id: string
  entry_date: string
  description: string
  category: string
  entry_type: 'income' | 'expense'
  amount: string
  source: string
  confidence: number
  raw_file_path: string | null
  created_at: string
}

export interface WalletTransaction {
  id: string
  transaction_type: string
  credits_delta: number
  feature: string
  paystack_reference: string | null
  status: string | null
  created_at: string
}

export interface Wallet {
  id: string
  balance: number
  auto_topup_threshold: number | null
  updated_at: string
  transactions: WalletTransaction[]
}

export interface MonoTransaction {
  id: string
  narration: string
  amount: number    // kobo
  type: 'credit' | 'debit'
  balance: number   // kobo
  date: string      // ISO string
  category: string | null
}

/* ── Liveness + face matching (/auth/me/liveness/*) ─────────────────── */
export type LivenessPurpose = 'enrol' | 'verify'

export interface LivenessStart {
  session_id: string
  purpose: LivenessPurpose
  challenges: string[]
  instructions: string[]
  expires_at: string
}

export interface LivenessFrameState {
  status: 'in_progress' | 'passed' | 'failed'
  done: boolean
  current_challenge: string | null
  remaining: number
  fail_reason: string | null
  face_count: number
}

export interface LivenessCompleteResult {
  purpose: LivenessPurpose
  passed: boolean
  enrolled: boolean
  matched: boolean | null
  score: number | null
  face_quality: number | null
  message: string
}

/* ── Hosted business verification (/verify/:token) ──────────────────── */
export interface HostedStep {
  type: 'nin' | 'bvn' | 'liveness' | 'reverify'
  status: 'pending' | 'passed' | 'failed' | 'needs_review' | 'error'
  reasons: string[]
  attempts_left: number
  source: 'this_session' | 'foid_credential'
}

export interface HostedSession {
  id: string
  env: 'test' | 'live'
  business: {
    name: string
    logo_url: string | null
    brand_color: string | null
    website: string | null
    support_email: string | null
  }
  purpose: string
  scopes: { scope: string; description: string }[]
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled' | 'expired'
  outcome: 'passed' | 'failed' | 'needs_review' | null
  consent_given: boolean
  reused_foid_credential: boolean
  steps: HostedStep[]
  person: { first_name: string | null }
  expires_at: string
  redirect_url?: string | null
}

export interface HostedStepResult {
  type: string
  status: HostedStep['status']
  reasons: string[]
}

/** A business with (or that had) access to the user's data — GET /connected-apps */
export interface ConnectedApp {
  org_id: string
  sandbox: boolean
  name: string
  logo_url: string | null
  website: string | null
  status: 'active' | 'revoked'
  scopes: { scope: string; description: string }[]
  first_connected_at: string | null
  verified_before_joining_foid: boolean
  grants: {
    id: string
    scopes: string[]
    purpose: string
    source: 'hosted_flow' | 'business_attested'
    status: 'active' | 'revoked'
    granted_at: string | null
    revoked_at: string | null
    revoked_by: string | null
  }[]
  checks: { type: string; status: string; at: string | null }[]
}
