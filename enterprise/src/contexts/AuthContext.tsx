/**
 * Business console session (backend /api/v1/console/auth/*).
 * A console account is NOT a FOID user account — separate login, tokens and password.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, apiErrorMessage, clearTokens, getRefreshToken, restoreSession, setTokens } from '@/lib/api'

export interface Member {
  id: string
  first_name: string
  last_name: string
  email: string
  email_verified: boolean
  two_factor_enabled: boolean
  created_at: string
}

export type Result = { ok: true } | { ok: false; error: string }
/** login: when two-step sign-in is on, `mfa` carries the 5-minute ticket for completeMfa() */
export type LoginResult = Result | { ok: false; mfa: string; error?: undefined }

interface Tokens { access_token: string; refresh_token: string }

interface AuthState {
  member: Member | null
  loading: boolean
  login: (email: string, password: string) => Promise<LoginResult>
  completeMfa: (mfaToken: string, code: string) => Promise<Result>
  /** sign in with tokens obtained elsewhere (accepting an invite creates the account) */
  adoptTokens: (access: string, refresh: string) => Promise<void>
  refreshMember: () => Promise<void>
  signup: (body: { first_name: string; last_name: string; email: string; password: string; company_name: string }) => Promise<Result>
  logout: () => Promise<void>
  verifyEmail: (code: string) => Promise<Result>
  resendVerification: () => Promise<Result>
}

const Ctx = createContext<AuthState | null>(null)

const fail = (e: unknown, fallback?: string): Result => ({ ok: false, error: apiErrorMessage(e, fallback) })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [member, setMember] = useState<Member | null>(null)
  const [loading, setLoading] = useState(true)

  const loadMe = useCallback(async () => {
    setMember((await api.get<Member>('/console/auth/me')).data)
  }, [])

  useEffect(() => {
    restoreSession()
      .then(async ok => { if (ok) await loadMe().catch(() => clearTokens()) })
      .finally(() => setLoading(false))
  }, [loadMe])

  const start = useCallback(async (path: string, body: object): Promise<Result> => {
    try {
      const t = (await api.post<Tokens>(path, body)).data
      setTokens(t.access_token, t.refresh_token)
      await loadMe()
      return { ok: true }
    } catch (e) {
      return fail(e)
    }
  }, [loadMe])

  const value: AuthState = {
    member,
    loading,
    login: async (email, password) => {
      try {
        const r = (await api.post<Tokens & { mfa_required?: boolean; mfa_token?: string }>('/console/auth/login', { email, password })).data
        if (r.mfa_required && r.mfa_token) return { ok: false, mfa: r.mfa_token }
        setTokens(r.access_token, r.refresh_token)
        await loadMe()
        return { ok: true }
      } catch (e) { return fail(e) }
    },
    completeMfa: (mfa_token, code) => start('/console/auth/login/2fa', { mfa_token, code }),
    adoptTokens: async (access, refresh) => { setTokens(access, refresh); await loadMe() },
    refreshMember: loadMe,
    signup: body => start('/console/auth/signup', body),
    logout: async () => {
      const rt = getRefreshToken()
      if (rt) await api.post('/console/auth/logout', { refresh_token: rt }).catch(() => {})
      clearTokens()
      setMember(null)
    },
    verifyEmail: async code => {
      try {
        setMember((await api.post<Member>('/console/auth/verify-email', { code })).data)
        return { ok: true }
      } catch (e) { return fail(e) }
    },
    resendVerification: async () => {
      try { await api.post('/console/auth/resend-verification'); return { ok: true } } catch (e) { return fail(e) }
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}
