/**
 * Sign-in apps — "Continue with FOID". One app per website / mobile app per mode:
 * public client id (goes in your frontend), client secret (server only, shown once),
 * allowed origins + redirect URIs, scopes, and optionally a public key (private_key_jwt).
 */
import { useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import Modal, { Confirm, SecretOnce, inputCls } from '@/components/Modal'
import { Button, PageHeader, Panel, Pill } from '@/components/ui'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'
import { ago, shortDate, useFetch } from '@/lib/useFetch'

interface Secret { id: string; hint: string; created_at: string; expires_at: string | null; last_used_at: string | null }
interface App {
  id: string; env: string; name: string; client_id: string; origins: string[]; redirect_uris: string[]
  scopes: string[]; auth_method: 'client_secret' | 'private_key_jwt'; public_jwk: Record<string, string> | null
  loopback_allowed: boolean; created_at: string; secrets: Secret[]
}
type Dialog =
  | { kind: 'create' } | { kind: 'edit'; app: App } | { kind: 'rotate' | 'delete'; app: App }
  | { kind: 'revoke-secret'; app: App; secret: Secret } | { kind: 'secret'; secret: string }

const lines = (s: string) => s.split(/[\n,]/).map(x => x.trim()).filter(Boolean)
const rowCls = 'flex flex-col gap-4 px-6 py-5 border-b border-neutral-200 last:border-0'
const smallBtn = 'w-full sm:w-36 py-2 rounded-full border text-[13px] font-semibold'
const hoursLeft = (iso: string) => Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000))

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button onClick={() => { void navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500) }}
      className="inline-flex items-center gap-1 text-[12px] font-semibold text-brand-600 hover:opacity-80">
      <RemixIcon name={done ? 'ri-check-line' : 'ri-file-copy-line'} size={13} /> {done ? 'Copied' : 'Copy'}
    </button>
  )
}

export default function AppsPage() {
  const { org, mode, can } = useMode()
  const base = org ? `/business/organisations/${org.id}/apps` : null
  const isDev = can('developer')
  const apps = useFetch<App[]>(isDev && base ? `${base}?env=${mode}` : null)
  const scopes = useFetch<Record<string, string>>('/business/oauth-scopes')
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [form, setForm] = useState({ name: '', origins: '', redirects: '', scopes: ['profile'] as string[],
                                     method: 'client_secret' as App['auth_method'], jwk: '' })

  const open = (d: Dialog) => {
    setErr('')
    if (d.kind === 'edit') {
      const a = d.app
      setForm({ name: a.name, origins: a.origins.join('\n'), redirects: a.redirect_uris.join('\n'), scopes: a.scopes,
                method: a.auth_method, jwk: a.public_jwk ? JSON.stringify(a.public_jwk, null, 2) : '' })
    } else if (d.kind === 'create') {
      setForm({ name: '', origins: '', redirects: '', scopes: ['profile'], method: 'client_secret', jwk: '' })
    }
    setDialog(d)
  }
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr('')
    try { await fn() } catch (e) { setErr(apiErrorMessage(e)) } finally { setBusy(false) }
  }

  const create = () => run(async () => {
    const r = await api.post<{ client_secret: string }>(base!, {
      env: mode, name: form.name.trim(), origins: lines(form.origins), redirect_uris: lines(form.redirects), scopes: form.scopes })
    await apps.reload(); setDialog({ kind: 'secret', secret: r.data.client_secret })
  })
  const save = (a: App) => {
    let jwk: Record<string, unknown> | undefined
    if (form.method === 'private_key_jwt' && form.jwk.trim()) {
      try { jwk = JSON.parse(form.jwk) as Record<string, unknown> } catch { setErr('The public key must be a JWK (JSON).'); return }
    }
    return run(async () => {
    await api.patch(`${base}/${a.id}`, {
      name: form.name.trim(), origins: lines(form.origins), redirect_uris: lines(form.redirects), scopes: form.scopes,
      ...(jwk ? { public_jwk: jwk } : {}), auth_method: form.method })
    await apps.reload(); setDialog(null)
    })
  }
  const rotate = (a: App) => run(async () => {
    const r = await api.post<{ client_secret: string }>(`${base}/${a.id}/secrets`)
    await apps.reload(); setDialog({ kind: 'secret', secret: r.data.client_secret })
  })
  const revokeSecret = (a: App, s: Secret) => run(async () => { await api.delete(`${base}/${a.id}/secrets/${s.id}`); await apps.reload(); setDialog(null) })
  const remove = (a: App) => run(async () => { await api.delete(`${base}/${a.id}`); await apps.reload(); setDialog(null) })

  const formFields = (
    <>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold">App name <span className="font-normal text-neutral-500">(people see this when they approve)</span>
        <input className={inputCls} placeholder="e.g. Acme Lending web" value={form.name} maxLength={60} autoFocus
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Allowed origins <span className="font-normal text-neutral-500">(where the button runs; one per line)</span>
        <textarea className={`${inputCls} font-mono text-[12.5px]`} rows={2} placeholder="https://app.acme.com"
          value={form.origins} onChange={e => setForm(f => ({ ...f, origins: e.target.value }))} />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Redirect URIs <span className="font-normal text-neutral-500">(for the no-popup fallback; exact match)</span>
        <textarea className={`${inputCls} font-mono text-[12.5px]`} rows={2} placeholder="https://app.acme.com/auth/foid/callback"
          value={form.redirects} onChange={e => setForm(f => ({ ...f, redirects: e.target.value }))} />
      </label>
      <p className="text-[12px] text-neutral-500 -mt-1">
        {mode === 'test' ? 'Test mode: http://localhost and http://127.0.0.1 work on any port without adding them.'
          : 'Live mode: https only, and every origin and redirect must match exactly.'}
      </p>
      <div className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold">What the app may ask for</span>
        {Object.entries(scopes.data ?? {}).map(([s, desc]) => (
          <label key={s} className="flex items-start gap-2 text-[12.5px]">
            <input type="checkbox" className="accent-[#C800DE] mt-0.5" disabled={s === 'profile'} checked={form.scopes.includes(s)}
              onChange={ev => setForm(f => ({ ...f, scopes: ev.target.checked ? [...f.scopes, s] : f.scopes.filter(x => x !== s) }))} />
            <span><b className="font-semibold capitalize">{s}</b> — {desc}</span>
          </label>
        ))}
      </div>
    </>
  )

  return (
    <div className="pb-8 flex flex-col gap-6">
      <PageHeader title="Sign-in apps" subtitle="“Continue with FOID” — people sign in and share their verified identity with your app">
        {isDev && <Button icon="ri-add-line" onClick={() => open({ kind: 'create' })}>Create {mode} app</Button>}
      </PageHeader>

      <Panel title="Apps" subtitle={mode === 'live'
        ? 'Live apps return real, verified identities — keep client secrets on your server'
        : 'Test apps: real FOID sign-in, real name only — everything else is dummy data'}>
        {!isDev && <p className="px-6 py-5 text-[13px] text-neutral-500">Only developers, admins and owners can manage sign-in apps.</p>}
        {apps.error && <p className="px-6 py-5 text-[13px] text-red-500">{apps.error}</p>}
        {apps.data?.length === 0 && <p className="px-6 py-5 text-[13px] text-neutral-500">No {mode} apps yet.</p>}
        {apps.data?.map(a => (
          <div key={a.id} className={rowCls}>
            <div className="flex flex-col sm:flex-row sm:items-start gap-4">
              <span className="w-10 h-10 rounded-xl bg-brand-100 flex items-center justify-center shrink-0">
                <RemixIcon name="ri-login-circle-line" size={20} color="#C800DE" />
              </span>
              <div className="flex-1 min-w-0 flex flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold">{a.name}</span>
                  <Pill tone={a.env === 'live' ? 'success' : 'brand'}>{a.env === 'live' ? 'Live' : 'Test'}</Pill>
                  <Pill tone="neutral">{a.auth_method === 'private_key_jwt' ? 'Key pair' : 'Client secret'}</Pill>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="text-neutral-500">Client ID</span>
                  <code className="font-mono text-neutral-800 break-all">{a.client_id}</code><Copy text={a.client_id} />
                </div>
                <div className="text-[12px] text-neutral-600">
                  <span className="text-neutral-500">Origins: </span>{a.origins.length ? a.origins.join(', ') : '—'}
                  {a.loopback_allowed && <span className="text-neutral-400"> (+ localhost)</span>}
                </div>
                <div className="text-[12px] text-neutral-600 break-all">
                  <span className="text-neutral-500">Redirects: </span>{a.redirect_uris.length ? a.redirect_uris.join(', ') : '—'}
                </div>
                <div className="flex flex-wrap gap-1">
                  {a.scopes.map(s => <span key={s} className="text-[11px] text-neutral-500 bg-neutral-100 rounded px-1.5 capitalize">{s}</span>)}
                </div>
                {a.auth_method === 'client_secret' && (
                  <div className="flex flex-col gap-1 mt-1">
                    {a.secrets.length === 0 && <span className="text-[12px] text-orange-600">No working client secret — create one.</span>}
                    {a.secrets.map(s => (
                      <div key={s.id} className="flex flex-wrap items-center gap-2 text-[12px]">
                        <RemixIcon name="ri-key-2-line" size={13} color="#a1a1aa" />
                        <code className="font-mono" title="Only the start and end are kept — the full secret was shown once">{s.hint}</code>
                        <span className="text-neutral-500">{s.last_used_at ? `used ${ago(s.last_used_at)}` : 'never used'} · created {shortDate(s.created_at)}</span>
                        {s.expires_at && <span className="text-orange-600">stops working in {hoursLeft(s.expires_at)} h</span>}
                        <button className="text-red-600 font-semibold hover:opacity-80" onClick={() => open({ kind: 'revoke-secret', app: a, secret: s })}>Revoke</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex sm:flex-col gap-2">
                <button className={`${smallBtn} border-neutral-200`} onClick={() => open({ kind: 'edit', app: a })}>Edit</button>
                {a.auth_method === 'client_secret' && (
                  <button className={`${smallBtn} border-neutral-200`} onClick={() => open({ kind: 'rotate', app: a })}>New secret</button>
                )}
                <button className={`${smallBtn} border-red-300 bg-red-50 text-red-600`} onClick={() => open({ kind: 'delete', app: a })}>Delete</button>
              </div>
            </div>
          </div>
        ))}
      </Panel>

      {dialog?.kind === 'create' && (
        <Modal title={`Create a ${mode} app`} onClose={() => setDialog(null)}>
          {formFields}
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={form.name.trim().length < 2 || busy ? 'opacity-50 pointer-events-none' : ''}>
            <Button onClick={() => void create()}>{busy ? 'Creating…' : 'Create app'}</Button>
          </span>
        </Modal>
      )}
      {dialog?.kind === 'edit' && (
        <Modal title={`Edit ${dialog.app.name}`} onClose={() => setDialog(null)}>
          {formFields}
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">How your server proves it's you</span>
            {(['client_secret', 'private_key_jwt'] as const).map(m => (
              <label key={m} className="flex items-start gap-2 text-[12.5px]">
                <input type="radio" className="accent-[#C800DE] mt-0.5" checked={form.method === m} onChange={() => setForm(f => ({ ...f, method: m }))} />
                <span>{m === 'client_secret'
                  ? <><b className="font-semibold">Client secret</b> — simplest; keep it on your server.</>
                  : <><b className="font-semibold">Key pair (private_key_jwt)</b> — recommended for banks: your server signs with a private key, FOID only holds the public key.</>}</span>
              </label>
            ))}
          </div>
          {form.method === 'private_key_jwt' && (
            <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Public key (JWK, EC P-256 or RSA 2048+)
              <textarea className={`${inputCls} font-mono text-[11.5px]`} rows={5} placeholder='{"kty":"EC","crv":"P-256","x":"…","y":"…"}'
                value={form.jwk} onChange={e => setForm(f => ({ ...f, jwk: e.target.value }))} />
              <span className="font-normal text-[12px] text-neutral-500">The FOID SDKs generate this for you. Never paste the private key.</span>
            </label>
          )}
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={busy ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void save(dialog.app)}>{busy ? 'Saving…' : 'Save'}</Button></span>
        </Modal>
      )}
      {dialog?.kind === 'rotate' && (
        <Modal title="New client secret" onClose={() => setDialog(null)}>
          <Confirm text={<>A new secret is created for <b>{dialog.app.name}</b>. The current one keeps working for <b>24 hours</b> so you can redeploy, then stops.</>}
            action="Create secret" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void rotate(dialog.app)} />
        </Modal>
      )}
      {dialog?.kind === 'revoke-secret' && (
        <Modal title="Revoke client secret" onClose={() => setDialog(null)}>
          <Confirm danger text={<><b>{dialog.secret.hint}</b> stops working immediately. Sign-ins finishing on a server that still uses it will fail.</>}
            action="Revoke" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void revokeSecret(dialog.app, dialog.secret)} />
        </Modal>
      )}
      {dialog?.kind === 'delete' && (
        <Modal title="Delete app" onClose={() => setDialog(null)}>
          <Confirm danger text={<>“Continue with FOID” stops working for <b>{dialog.app.name}</b> and its secrets are revoked. People who already shared with you keep their consent until they revoke it.</>}
            action="Delete app" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void remove(dialog.app)} />
        </Modal>
      )}
      {dialog?.kind === 'secret' && (
        <Modal title="Copy it now" onClose={() => setDialog(null)}>
          <SecretOnce secret={dialog.secret} what="client secret" onDone={() => setDialog(null)} />
        </Modal>
      )}
    </div>
  )
}
