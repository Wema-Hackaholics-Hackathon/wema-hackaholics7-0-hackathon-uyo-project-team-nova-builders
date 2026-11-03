import { useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import Modal, { Confirm, SecretOnce, inputCls } from '@/components/Modal'
import { Button, PageHeader, Panel, Pill } from '@/components/ui'
import { docsLink } from '@/lib/docs'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'
import { ago, shortDate, useFetch } from '@/lib/useFetch'

interface Key { id: string; env: string; name: string; hint: string; last_used_at: string | null; created_at: string }
interface Hook {
  id: string; env: string; url: string; events: string[]; enabled: boolean; created_at: string
  last_delivery_status: string | null; last_delivery_at: string | null
}
type Dialog =
  | { kind: 'create-key' } | { kind: 'rotate-key' | 'revoke-key'; key: Key }
  | { kind: 'add-hook' } | { kind: 'roll-hook' | 'delete-hook'; hook: Hook }
  | { kind: 'secret'; secret: string; what: string }

function Meta({ used, created }: { used: string; created: string }) {
  return (
    <div className="text-[11px] text-neutral-600 leading-snug sm:text-right whitespace-nowrap">
      <div>{used}</div><div>Created {created}</div>
    </div>
  )
}

const rowCls = 'flex flex-col sm:flex-row sm:items-center gap-4 px-6 py-5 border-b border-neutral-200 last:border-0'
const smallBtn = 'w-full sm:w-36 py-2 rounded-full border text-[13px] font-semibold'

export default function ApiKeysPage() {
  const { org, mode, can } = useMode()
  const base = org ? `/business/organisations/${org.id}` : null
  const isDev = can('developer')
  const keys = useFetch<Key[]>(isDev && base ? `${base}/api-keys?env=${mode}` : null)
  const hooks = useFetch<Hook[]>(isDev && base ? `${base}/webhooks?env=${mode}` : null)
  const events = useFetch<string[]>('/business/webhook-event-types')
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [testResult, setTestResult] = useState<Record<string, string>>({})

  const open = (d: Dialog) => { setErr(''); setName(''); setUrl(''); setPicked([]); setDialog(d) }
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr('')
    try { await fn() } catch (e) { setErr(apiErrorMessage(e)) } finally { setBusy(false) }
  }
  const showSecret = (secret: string, what: string) => setDialog({ kind: 'secret', secret, what })

  const createKey = () => run(async () => {
    const r = await api.post<{ secret: string }>(`${base}/api-keys`, { env: mode, name: name.trim() || 'Default key' })
    await keys.reload(); showSecret(r.data.secret, 'API key')
  })
  const rotateKey = (k: Key) => run(async () => {
    const r = await api.post<{ secret: string }>(`${base}/api-keys/${k.id}/rotate`)
    await keys.reload(); showSecret(r.data.secret, 'API key')
  })
  const revokeKey = (k: Key) => run(async () => { await api.delete(`${base}/api-keys/${k.id}`); await keys.reload(); setDialog(null) })
  const addHook = () => run(async () => {
    const r = await api.post<{ secret: string }>(`${base}/webhooks`, { env: mode, url: url.trim(), events: picked.length ? picked : ['*'] })
    await hooks.reload(); showSecret(r.data.secret, 'signing secret')
  })
  const rollHook = (h: Hook) => run(async () => {
    const r = await api.post<{ secret: string }>(`${base}/webhooks/${h.id}/roll-secret`)
    showSecret(r.data.secret, 'signing secret')
  })
  const deleteHook = (h: Hook) => run(async () => { await api.delete(`${base}/webhooks/${h.id}`); await hooks.reload(); setDialog(null) })
  const testHook = async (h: Hook) => {
    setTestResult(t => ({ ...t, [h.id]: 'Sending…' }))
    try {
      const d = (await api.post<{ status: string; last_status_code: number | null; last_error: string | null }>(`${base}/webhooks/${h.id}/test`)).data
      setTestResult(t => ({ ...t, [h.id]: d.status === 'delivered' ? `Test delivered (HTTP ${d.last_status_code})` : `Test failed: ${d.last_error ?? d.last_status_code ?? 'no response'}` }))
      await hooks.reload()
    } catch (e) { setTestResult(t => ({ ...t, [h.id]: apiErrorMessage(e) })) }
  }

  return (
    <div className="pb-8 flex flex-col gap-6">
      <PageHeader title="API keys & webhooks" subtitle="Manage credentials and real-time event delivery for your integration">
        <Button variant="outline" icon="ri-book-open-line" onClick={() => window.open(docsLink('/guide/quickstart'), '_blank', 'noopener')}>Docs</Button>
        {isDev && <Button icon="ri-add-line" onClick={() => open({ kind: 'create-key' })}>Create {mode} key</Button>}
      </PageHeader>

      <Panel title="API keys" subtitle={mode === 'live' ? 'Live keys act on real user data — keep them server-side only' : 'Test keys only touch sandbox data — use them while you build'}>
        {!isDev && <p className="px-6 py-5 text-[13px] text-neutral-500">Only developers, admins and owners can manage API keys and webhooks.</p>}
        {keys.error && <p className="px-6 py-5 text-[13px] text-red-500">{keys.error}</p>}
        {keys.data?.length === 0 && <p className="px-6 py-5 text-[13px] text-neutral-500">No {mode} keys yet.</p>}
        {keys.data?.map(k => (
          <div key={k.id} className={rowCls}>
            <span className="w-10 h-10 rounded-xl bg-brand-100 flex items-center justify-center shrink-0">
              <RemixIcon name="ri-key-2-line" size={20} color="#C800DE" />
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[15px] font-semibold">{k.name}</span>
                <Pill tone={k.env === 'live' ? 'success' : 'brand'}>{k.env === 'live' ? 'Live' : 'Test'}</Pill>
              </div>
              <div className="text-[12px] text-neutral-600 font-mono" title="Only the start and end are kept — the full key was shown once">{k.hint}</div>
            </div>
            <Meta used={k.last_used_at ? `Used ${ago(k.last_used_at)}` : 'Never used'} created={shortDate(k.created_at)} />
            <div className="flex sm:flex-col gap-2">
              <button className={`${smallBtn} border-neutral-200`} onClick={() => open({ kind: 'rotate-key', key: k })}>Regenerate</button>
              <button className={`${smallBtn} border-red-300 bg-red-50 text-red-600`} onClick={() => open({ kind: 'revoke-key', key: k })}>Revoke</button>
            </div>
          </div>
        ))}
      </Panel>

      {isDev && (
        <Panel title="Webhook endpoints" subtitle="Get notified the moment a user's status changes"
          action={<button onClick={() => open({ kind: 'add-hook' })} className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-neutral-200 text-[12.5px] font-semibold">
            <RemixIcon name="ri-add-line" size={14} /> Add endpoint</button>}>
          {hooks.error && <p className="px-6 py-5 text-[13px] text-red-500">{hooks.error}</p>}
          {hooks.data?.length === 0 && <p className="px-6 py-5 text-[13px] text-neutral-500">No {mode} endpoints yet.</p>}
          {hooks.data?.map(w => (
            <div key={w.id} className={rowCls}>
              <RemixIcon name="ri-webhook-line" size={20} color={w.last_delivery_status === 'delivered' ? '#16a34a' : w.last_delivery_status ? '#ef4444' : '#a1a1aa'} />
              <div className="flex-1 min-w-0">
                <div className="text-[15px] font-semibold truncate">{w.url}</div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {w.events.map(e => <span key={e} className="text-[11px] text-neutral-500 bg-neutral-100 rounded px-1.5">{e === '*' ? 'all events' : e}</span>)}
                </div>
                {testResult[w.id] && <div className="text-[12px] text-neutral-600 mt-1">{testResult[w.id]}</div>}
              </div>
              <Meta used={w.last_delivery_at ? `${w.last_delivery_status === 'delivered' ? 'Delivered' : 'Failed'} ${ago(w.last_delivery_at)}` : 'No deliveries yet'} created={shortDate(w.created_at)} />
              <div className="flex sm:flex-col gap-2">
                <button className={`${smallBtn} border-neutral-200`} onClick={() => void testHook(w)}>Send test</button>
                <button className={`${smallBtn} border-neutral-200`} onClick={() => open({ kind: 'roll-hook', hook: w })}>Rotate secret</button>
                <button className={`${smallBtn} border-red-300 bg-red-50 text-red-600`} onClick={() => open({ kind: 'delete-hook', hook: w })}>Delete</button>
              </div>
            </div>
          ))}
        </Panel>
      )}

      {dialog?.kind === 'create-key' && (
        <Modal title={`Create a ${mode} key`} onClose={() => setDialog(null)}>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">Name
            <input className={inputCls} placeholder="e.g. Production backend" value={name} onChange={e => setName(e.target.value)} maxLength={60} autoFocus />
          </label>
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={busy ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void createKey()}>{busy ? 'Creating…' : 'Create key'}</Button></span>
        </Modal>
      )}
      {dialog?.kind === 'rotate-key' && (
        <Modal title="Regenerate key" onClose={() => setDialog(null)}>
          <Confirm text={<><b>{dialog.key.name}</b> ({dialog.key.hint}) stops working immediately and a new key replaces it. Update your servers right after.</>}
            action="Regenerate" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void rotateKey(dialog.key)} />
        </Modal>
      )}
      {dialog?.kind === 'revoke-key' && (
        <Modal title="Revoke key" onClose={() => setDialog(null)}>
          <Confirm danger text={<><b>{dialog.key.name}</b> ({dialog.key.hint}) stops working immediately. This can’t be undone.</>}
            action="Revoke key" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void revokeKey(dialog.key)} />
        </Modal>
      )}
      {dialog?.kind === 'add-hook' && (
        <Modal title={`Add a ${mode} endpoint`} onClose={() => setDialog(null)}>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold">URL
            <input className={inputCls} placeholder="https://api.yourapp.com/hooks/foid" value={url} onChange={e => setUrl(e.target.value)} autoFocus />
          </label>
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Events <span className="font-normal text-neutral-500">(none ticked = all)</span></span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {events.data?.map(e => (
                <label key={e} className="flex items-center gap-2 text-[12.5px]">
                  <input type="checkbox" className="accent-[#C800DE]" checked={picked.includes(e)}
                    onChange={ev => setPicked(p => ev.target.checked ? [...p, e] : p.filter(x => x !== e))} />{e}
                </label>
              ))}
            </div>
          </div>
          {err && <p className="text-[13px] text-red-500">{err}</p>}
          <span className={!url.trim() || busy ? 'opacity-50 pointer-events-none' : ''}><Button onClick={() => void addHook()}>{busy ? 'Adding…' : 'Add endpoint'}</Button></span>
        </Modal>
      )}
      {dialog?.kind === 'roll-hook' && (
        <Modal title="Rotate signing secret" onClose={() => setDialog(null)}>
          <Confirm text={<>Events to <b>{dialog.hook.url}</b> will be signed with a new secret from now on. Update your server to verify with it.</>}
            action="Rotate secret" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void rollHook(dialog.hook)} />
        </Modal>
      )}
      {dialog?.kind === 'delete-hook' && (
        <Modal title="Delete endpoint" onClose={() => setDialog(null)}>
          <Confirm danger text={<>Stop sending events to <b>{dialog.hook.url}</b> and delete its delivery history?</>}
            action="Delete" busy={busy} error={err} onCancel={() => setDialog(null)} onConfirm={() => void deleteHook(dialog.hook)} />
        </Modal>
      )}
      {dialog?.kind === 'secret' && (
        <Modal title="Copy it now" onClose={() => setDialog(null)}>
          <SecretOnce secret={dialog.secret} what={dialog.what} onDone={() => setDialog(null)} />
        </Modal>
      )}
    </div>
  )
}
