// Where the FOID docs site lives (docs/, port 5177 locally). Set VITE_DOCS_URL in production.
export const DOCS_URL = ((import.meta.env.VITE_DOCS_URL as string | undefined) || 'http://localhost:5177').replace(/\/$/, '')
export const docsLink = (path = '/') => `${DOCS_URL}${path.startsWith('/') ? path : `/${path}`}`
