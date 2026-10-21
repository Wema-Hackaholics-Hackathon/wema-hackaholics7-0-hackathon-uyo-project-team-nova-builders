/** Credential state machine states */
export type CredentialState = 'active' | 'under_review' | 'downgraded' | 'revoked'

/** Core credential claims (v1) */
export interface CredentialClaims {
  identity_verified: boolean
  bvn_validated: boolean
  age_over_18: boolean
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
  bvn?: string | null
  phone?: string | null
  address?: string | null
  email: string
  created_at: string
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
