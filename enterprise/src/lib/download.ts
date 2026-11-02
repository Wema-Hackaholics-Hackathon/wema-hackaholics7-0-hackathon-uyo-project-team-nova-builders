import { api } from './api'

/** Fetch a file with the console session (auth header) and save it under the server's filename. */
export async function download(path: string, fallbackName = 'export.csv') {
  const res = await api.get<Blob>(path, { responseType: 'blob' })
  const disposition = String(res.headers['content-disposition'] ?? '')
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName
  const url = URL.createObjectURL(res.data)
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
