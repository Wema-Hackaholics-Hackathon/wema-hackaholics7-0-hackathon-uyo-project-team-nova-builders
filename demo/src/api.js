// Harbor's own backend (Python or Node — whichever served this page). Same origin, so no CORS
// and no secrets in the browser: only the public client IDs come back from /api/config.
export class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || `HTTP ${status}`)
    this.status = status
    this.code = error?.code || 'error'
    this.body = error?.body ?? null
  }
}

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = { message: text } }
  if (!res.ok) throw new ApiError(res.status, data?.error ?? data)
  return data
}

const qs = (params) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v))
  return q.size ? `?${q}` : ''
}

export const api = {
  config: () => call('GET', '/api/config'),
  ping: () => call('GET', '/api/ping'),
  keypair: () => call('GET', '/api/keypair'),
  makeKeypair: () => call('POST', '/api/keypair'),

  createVerification: (b) => call('POST', '/api/verifications', b),
  listVerifications: (f = {}) => call('GET', `/api/verifications${qs(f)}`),
  getVerification: (id) => call('GET', `/api/verifications/${id}`),
  cancelVerification: (id) => call('POST', `/api/verifications/${id}/cancel`, {}),

  check: (kind, b) => call('POST', `/api/checks/${kind}`, b),

  listSubjects: (f = {}) => call('GET', `/api/subjects${qs(f)}`),
  getSubject: (id) => call('GET', `/api/subjects/${id}`),
  subjectChecks: (id) => call('GET', `/api/subjects/${id}/checks`),
  trustReport: (id) => call('GET', `/api/subjects/${id}/trust-report`),
  deleteSubject: (id) => call('DELETE', `/api/subjects/${id}`),

  signinStart: (b) => call('POST', '/api/signin/start', b),
  exchange: (b) => call('POST', '/api/signin/exchange', b),

  webhooks: () => call('GET', '/api/webhooks'),
  clearWebhooks: () => call('DELETE', '/api/webhooks'),
}
