import type { CSSProperties, ReactElement, ReactNode } from 'react'
import type { FoidSignInError, FoidSignInSuccess } from './core'
export * from './core'

export declare function FoidProvider(props: { clientId: string; foidUrl?: string; children?: ReactNode }): ReactElement

export interface FoidLoginOptions {
  scope?: string
  nonce?: string
  state?: string
  codeChallenge?: string
  redirectUri?: string
  onSuccess?: (result: FoidSignInSuccess) => void
  onError?: (error: FoidSignInError) => void
}
export declare function useFoidLogin(options?: FoidLoginOptions): (() => void) & { pending: boolean }

export declare function ContinueWithFoid(props: FoidLoginOptions & {
  text?: 'continue_with' | 'signin_with' | 'signup_with' | 'verify_with'
  theme?: 'filled' | 'outline'
  size?: 'small' | 'medium' | 'large'
  width?: number | string
  disabled?: boolean
  className?: string
  style?: CSSProperties
}): ReactElement

