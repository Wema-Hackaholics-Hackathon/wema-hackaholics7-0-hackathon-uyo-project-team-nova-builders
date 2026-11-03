export declare const DEFAULT_FOID_URL: string
export declare class FoidSignInError extends Error {
  /** popup_closed | popup_blocked | access_denied | state_mismatch | missing_client_id | unknown */
  code: string
}
export interface FoidSignInSuccess { code: string; state: string; codeVerifier: string | null }
export interface SignInOptions {
  clientId: string
  foidUrl?: string
  /** space-separated: profile (always) identity contact liveness financial */
  scope?: string
  nonce?: string
  state?: string
  /** your server's PKCE challenge; then codeVerifier comes back null (your server kept it) */
  codeChallenge?: string
  /** fallback when popups are blocked; must be registered on the app */
  redirectUri?: string
  width?: number
  height?: number
}
export declare function createPkcePair(): Promise<{ codeVerifier: string; codeChallenge: string }>
export declare function signInWithFoid(options: SignInOptions): Promise<FoidSignInSuccess>
export declare function handleRedirectCallback(search?: string): FoidSignInSuccess | null
