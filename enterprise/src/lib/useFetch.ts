import { useCallback, useEffect, useState } from 'react'
import { api, apiErrorMessage } from './api'

/** GET `path` (skipped while null); refetches when `path` changes. */
export function useFetch<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const reload = useCallback(async () => {
    if (!path) return
    setLoading(true)
    try {
      setData((await api.get<T>(path)).data)
      setError('')
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => { void reload() }, [reload])
  return { data, error, loading, reload }
}

/** "4 min ago", "Yesterday", "12 Jun" */
export function ago(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} hr${s >= 7200 ? 's' : ''} ago`
  if (s < 172800) return 'Yesterday'
  return shortDate(iso)
}

export function shortDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}
