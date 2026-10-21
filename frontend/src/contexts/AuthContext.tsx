import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import type { User } from '../types/foid'
import { api, setTokens, clearTokens, restoreSession } from '../lib/api'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  loading: boolean
  login: (email: string, password: string) => Promise<boolean>
  signup: (userData: {
    firstName: string
    lastName: string
    middleName?: string
    nin: string
    email: string
    password: string
  }) => Promise<boolean>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function normaliseUser(raw: Record<string, unknown>): User {
  return {
    ...(raw as unknown as User),
    firstName: (raw.first_name as string) ?? '',
    lastName: (raw.last_name as string) ?? '',
    middleName: (raw.middle_name as string | null) ?? null,
    createdAt: (raw.created_at as string) ?? '',
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // On mount — try to restore session from the persisted refresh token
  useEffect(() => {
    restoreSession().then(async ok => {
      if (ok) {
        try {
          const res = await api.get<Record<string, unknown>>('/auth/me')
          setUser(normaliseUser(res.data))
        } catch {
          clearTokens()
        }
      }
      setLoading(false)
    })
  }, [])

  const signup = useCallback(async (userData: {
    firstName: string
    lastName: string
    middleName?: string
    nin: string
    email: string
    password: string
  }): Promise<boolean> => {
    try {
      const res = await api.post<{ access_token: string; refresh_token: string }>(
        '/auth/signup',
        {
          first_name: userData.firstName,
          last_name: userData.lastName,
          middle_name: userData.middleName || null,
          nin: userData.nin,
          email: userData.email,
          password: userData.password,
        }
      )
      setTokens(res.data.access_token, res.data.refresh_token)
      const meRes = await api.get<Record<string, unknown>>('/auth/me')
      setUser(normaliseUser(meRes.data))
      return true
    } catch {
      return false
    }
  }, [])

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    try {
      const res = await api.post<{ access_token: string; refresh_token: string }>(
        '/auth/login',
        { email, password }
      )
      setTokens(res.data.access_token, res.data.refresh_token)
      const meRes = await api.get<Record<string, unknown>>('/auth/me')
      setUser(normaliseUser(meRes.data))
      return true
    } catch {
      return false
    }
  }, [])

  const logout = useCallback(async (): Promise<void> => {
    try {
      const stored = localStorage.getItem('idra_refresh_token')
      if (stored) {
        await api.post('/auth/logout', { refresh_token: stored })
      }
    } catch {
      // best-effort
    } finally {
      clearTokens()
      setUser(null)
    }
  }, [])

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const res = await api.get<Record<string, unknown>>('/auth/me')
      setUser(normaliseUser(res.data))
    } catch {
      // silently ignore — token may have expired
    }
  }, [])

  return (
    <AuthContext.Provider value={{
      user,
      isAuthenticated: user !== null,
      loading,
      login,
      signup,
      logout,
      refreshUser,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
