/**
 * Axios API client for the FOID backend (backend-2).
 *
 * - Base URL: Vite proxy forwards /api/* → http://localhost:8000
 * - Attaches Authorization: Bearer <access_token> to every request
 * - On 401, attempts one silent token refresh then retries the request
 * - Access token is kept in-memory only; refresh token persists in localStorage
 */
import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

const _rawBase = import.meta.env.VITE_API_BASE_URL as string | undefined
export const BASE_URL = (_rawBase ?? '').replace(/\/api\/v1\/?$/, '')

// ── In-memory token store ─────────────────────────────────────────────────
let _accessToken: string | null = null
let _refreshToken: string | null = null

export const TOKEN_KEY = 'idra_refresh_token'

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
