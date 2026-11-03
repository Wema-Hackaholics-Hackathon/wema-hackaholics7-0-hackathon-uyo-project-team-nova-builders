/**
 * Axios API client for the FOID backend (backend/).
 *
 * - Base URL: Vite proxy forwards /api/* → http://localhost:8000
 * - Attaches Authorization: Bearer <access_token> to every request
 * - On 401, attempts one silent token refresh then retries the request
 * - Access token is kept in-memory only; refresh token persists in localStorage
 */
import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

const _rawBase = import.meta.env.VITE_API_URL as string | undefined
export const BASE_URL = (_rawBase ?? '').replace(/\/api\/v1\/?$/, '')

// ── In-memory token store ─────────────────────────────────────────────────
let _accessToken: string | null = null
let _refreshToken: string | null = null

export const TOKEN_KEY = 'idra_refresh_token'

/** Random id for this browser (localStorage) — lets the server spot sign-ins from new devices. */
export function deviceId(): string {
  let id = localStorage.getItem('foid_device_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('foid_device_id', id)
  }
  return id
}

export function setTokens(access: string, refresh: string) {
  _accessToken = access
  _refreshToken = refresh
  localStorage.setItem(TOKEN_KEY, refresh)
}

export function clearTokens() {
  _accessToken = null
  _refreshToken = null
  localStorage.removeItem(TOKEN_KEY)
}

export function getAccessToken() {
  return _accessToken
}

/** Call once on app boot to restore session from persisted refresh token. */
export async function restoreSession(): Promise<boolean> {
  const stored = localStorage.getItem(TOKEN_KEY)
  if (!stored) return false
  _refreshToken = stored
  return _silentRefresh()
}

// ── Axios instance ────────────────────────────────────────────────────────
export const api = axios.create({ baseURL: `${BASE_URL}/api/v1` })

// Attach access token before every request
api.interceptors.request.use(config => {
  if (_accessToken) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${_accessToken}`
  }
  return config
})

// On 401 → try a silent refresh once, then retry
let _refreshing = false
let _refreshQueue: Array<(token: string | null) => void> = []

api.interceptors.response.use(
  res => res,
  async err => {
    const original: AxiosRequestConfig & { _retry?: boolean } = err.config
    if (err.response?.status !== 401 || original._retry) {
      return Promise.reject(err)
    }
    original._retry = true

    if (_refreshing) {
      // Queue concurrent requests until the refresh completes
      return new Promise((resolve, reject) => {
        _refreshQueue.push(token => {
          if (token) {
            original.headers = { ...original.headers, Authorization: `Bearer ${token}` }
            resolve(api(original))
          } else {
            reject(err)
          }
        })
      })
    }

    _refreshing = true
    const newToken = (await _silentRefresh()) ? _accessToken : null
    _refreshing = false
    _refreshQueue.forEach(cb => cb(newToken))
    _refreshQueue = []

    if (newToken) {
      original.headers = { ...original.headers, Authorization: `Bearer ${newToken}` }
      return api(original)
    }
    return Promise.reject(err)
  }
)

async function _silentRefresh(): Promise<boolean> {
  if (!_refreshToken) return false
  try {
    const res = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
      refresh_token: _refreshToken,
    })
    const { access_token, refresh_token } = res.data as {
      access_token: string
      refresh_token: string
    }
    setTokens(access_token, refresh_token)
    return true
  } catch {
    clearTokens()
    return false
  }
}

/**
 * Human-readable reason for a failed API call.
 * Network failure → names the server it tried; 5xx → the server's message if it
 * sent one (e.g. "database schema is out of date"), else a generic one;
 * 4xx → the backend's `detail` (string or first validation message) or Open-API `error.message`.
 */
export function apiErrorMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const e = err as {
    response?: { status?: number; data?: { detail?: unknown; error?: { message?: string } } }
  }
  if (!e?.response) {
    return `Can't reach the FOID server${BASE_URL ? ` at ${BASE_URL}` : ''}. Check that the backend is running.`
  }
  const { status = 0, data } = e.response
  const detail = data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown })?.msg
    if (typeof msg === 'string') return msg.replace(/^Value error, /, '')
  }
  if (data?.error?.message) return data.error.message
  if (status >= 500) return 'Something went wrong on our side. Please try again.'
  return fallback
}
