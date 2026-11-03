export declare const DEFAULT_BASE_URL: string

export declare class FoidError extends Error {
  status: number
  code: string
  description: string
  body: unknown
}

export interface FoidSignInResult {
  object: 'foid_sign_in'
  env: 'test' | 'live'
  sandbox: boolean
  nonce: string | null
  subject_id: string
  scopes: string[]
  foid_account: boolean
  face_rematched_at: string | null
  subject: Record<string, unknown> & { first_name?: string; last_name?: string; middle_name?: string | null }
  checks: { type: string; status: string; [k: string]: unknown }[]
}

export interface FoidOptions {
  apiKey?: string
  clientId?: string
  clientSecret?: string
  privateKeyPem?: string
  keyId?: string
  baseUrl?: string
  fetch?: typeof fetch
}

export declare function createPkce(): { codeVerifier: string; codeChallenge: string; state: string; nonce: string }
export declare function generateKeyPair(): { privateKeyPem: string; publicJwk: Record<string, string> }
export declare function clientAssertion(privateKeyPem: string, clientId: string, audience: string, kid?: string): string
export declare function verifyWebhook<T = unknown>(payload: Buffer | string, header: string, secret: string, toleranceSeconds?: number): T

export declare class Foid {
  constructor(options?: FoidOptions)
  oauth: { exchange(code: string, codeVerifier: string, opts?: { redirectUri?: string }): Promise<FoidSignInResult> }
  webhooks: { verify: typeof verifyWebhook }
  request<T = unknown>(method: string, path: string, opts?: { json?: unknown; params?: Record<string, string>; idempotencyKey?: string }): Promise<T>
  getSubject(id: string): Promise<Record<string, unknown>>
  createVerification(body: Record<string, unknown> & { idempotencyKey?: string }): Promise<Record<string, unknown>>
  getVerification(id: string): Promise<Record<string, unknown>>
  checkNin(body: Record<string, unknown>): Promise<Record<string, unknown>>
  checkBvn(body: Record<string, unknown>): Promise<Record<string, unknown>>
}
export default Foid
