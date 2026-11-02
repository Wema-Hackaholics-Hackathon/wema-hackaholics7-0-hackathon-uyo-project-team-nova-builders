/**
 * Usage & billing — per business. Paying goes through Bachs checkout; the invoice turns
 * "paid" only when Bachs confirms it to the backend (signed webhook), so after returning
 * from checkout this page waits for that confirmation. Prices are placeholders (backend PLANS).
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import RemixIcon from '@/components/RemixIcon'
import Modal from '@/components/Modal'
import { Button, PageHeader, Panel, Pill, Table } from '@/components/ui'
import { useMode } from '@/contexts/ModeContext'
import { api, apiErrorMessage } from '@/lib/api'
import { download } from '@/lib/download'
import { shortDate, useFetch } from '@/lib/useFetch'

interface Plan { code: string; name: string; price_ngn: number | null; limit: number | null; seats: number | null; features: string[] }
interface Usage {
  period_start: string; period_end: string; limit: number | null; projected_limit_date: string | null
  live: { total: number; by_check: Record<string, number> }; test: { total: number; by_check: Record<string, number> }
}
interface Invoice { id: string; number: string; kind: string; plan: string; period_start: string; period_end: string; amount_ngn: number; status: string; paid_at: string | null }
interface Billing { plan: Plan; usage: Usage; invoices: Invoice[] }

const naira = (n: number | null) => n == null ? 'Custom' : n === 0 ? 'Free' : `₦${n.toLocaleString('en-NG')}`
const CHECK = { nin: 'NIN checks', bvn: 'BVN checks', liveness: 'Liveness checks', reverify: 'Re-verifications' } as Record<string, string>

function Bar({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  return (
    <div>
      <div className="flex justify-between text-[14px] mb-2">
        <span className="font-medium">{label}</span>
        <span className="text-[12px] font-semibold">{used.toLocaleString()}{limit ? ` / ${limit.toLocaleString()}` : ''}</span>
      </div>
      <div className="h-1.5 rounded-full bg-neutral-100">
        <div className={`h-full rounded-full ${limit && used >= limit ? 'bg-red-500' : 'bg-[#C800DE]'}`}
          style={{ width: `${limit ? Math.min(100, (used / limit) * 100) : used ? 100 : 0}%` }} />
      </div>
    </div>
  )
}

export default function BillingPage() {
  const { org, can } = useMode()
  const [params, setParams] = useSearchParams()
  const base = org && can('admin') ? `/business/organisations/${org.id}` : null
  const { data, error, reload } = useFetch<Billing>(base && `${base}/billing`)
  const plans = useFetch<Plan[]>('/business/plans')
  const [picking, setPicking] = useState(false)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState<{ tone: 'wait' | 'ok' | 'warn'; text: string } | null>(null)

  // Back from Bachs: wait for the webhook to mark the invoice paid
  const returned = params.get('invoice')
  const cancelled = params.get('cancelled')
  useEffect(() => {
    if (cancelled) { setNotice({ tone: 'warn', text: 'Payment cancelled — nothing was charged.' }); setParams({}, { replace: true }); return }
    if (!returned || !base) return
    setNotice({ tone: 'wait', text: 'Confirming your payment with Bachs…' })
    let tries = 0
    const t = setInterval(async () => {
      tries += 1
      try {
        const inv = (await api.get<Invoice>(`${base}/invoices/${returned}`)).data
        if (inv.status === 'paid') {
          clearInterval(t); setParams({}, { replace: true }); await reload()
          setNotice({ tone: 'ok', text: `Payment received — you’re on ${inv.plan}.` })
        } else if (tries >= 40) {
          clearInterval(t)
          setNotice({ tone: 'warn', text: 'We haven’t heard from Bachs yet. If you paid, this page updates once they confirm — you can refresh later.' })
        }
      } catch { /* keep waiting */ }
    }, 3000)
    return () => clearInterval(t)
  }, [returned, cancelled, base])  // eslint-disable-line react-hooks/exhaustive-deps

  const go = async (key: string, fn: () => Promise<string | null>) => {
    setBusy(key); setErr('')
    try {
      const url = await fn()
      if (url) window.location.assign(url)          // to Bachs checkout
      else { setPicking(false); await reload() }
    } catch (e) { setErr(apiErrorMessage(e)) } finally { setBusy('') }
  }
  const choose = (code: string) => go(code, async () =>
    (await api.post<{ checkout_url: string | null }>(`${base}/billing/checkout`, { plan_code: code })).data.checkout_url)
  const pay = (inv: Invoice) => go(inv.id, async () =>
    (await api.post<{ checkout_url: string }>(`${base}/invoices/${inv.id}/pay`)).data.checkout_url)

  if (!can('admin')) {
    return (
      <div className="pb-8">
        <PageHeader title="Usage & billing" subtitle="Your plan, consumption, and invoice history" />
        <p className="text-[13px] text-neutral-500">Only owners and admins can see billing for {org?.name}.</p>
      </div>
    )
  }

  const u = data?.usage
  const plan = data?.plan
  const renews = data && plan?.code !== 'starter' && u ? `Renews ${shortDate(u.period_end)}` : 'Free plan — no card or transfer needed'

  return (
    <div className="pb-8 flex flex-col gap-6">
      <PageHeader title="Usage & billing" subtitle="Your plan, consumption, and invoice history">
        <Button icon="ri-arrow-up-circle-line" onClick={() => { setErr(''); setPicking(true) }}>Upgrade plan</Button>
      </PageHeader>

      {notice && (
        <p className={`flex gap-2 rounded-xl border p-4 text-[13px] ${notice.tone === 'ok' ? 'bg-green-50 border-green-200 text-green-700' : notice.tone === 'warn' ? 'bg-orange-50 border-orange-200 text-orange-700' : 'bg-brand-50 border-brand-200 text-brand-700'}`}>
          <RemixIcon name={notice.tone === 'ok' ? 'ri-checkbox-circle-line' : notice.tone === 'warn' ? 'ri-error-warning-line' : 'ri-loader-4-line'} size={18} />
          {notice.text}
        </p>
      )}
      {(error || (err && !picking)) && <p className="text-[13px] text-red-500">{error || err}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-6">
        <Panel title="This month's usage" subtitle={u ? `Live checks, ${shortDate(u.period_start)} – ${shortDate(u.period_end)}` : undefined}>
          <div className="p-6 flex flex-col gap-6">
            {u && <Bar label="Identity verifications" used={u.live.total} limit={u.limit} />}
            {u && Object.entries(u.live.by_check).map(([k, n]) => <Bar key={k} label={CHECK[k] ?? k} used={n} limit={null} />)}
            {u?.projected_limit_date && (
              <p className="flex gap-2 rounded-xl bg-neutral-100 p-4 text-[12.5px] text-neutral-600">
                <RemixIcon name="ri-information-line" size={18} color="#C800DE" />
                You’re projected to hit your verification limit around {shortDate(u.projected_limit_date)}. Consider upgrading to avoid throttling.
              </p>
            )}
            {u && <p className="text-[12px] text-neutral-500">Test mode: {u.test.total.toLocaleString()} checks this period — free, never billed.</p>}
          </div>
        </Panel>

        <Panel title={plan ? `${plan.name} plan` : 'Plan'}>
          <div className="p-6 flex flex-col gap-4">
            {plan && (
              <>
                <div>
                  <span className="text-[36px] font-bold">{naira(plan.price_ngn)}</span>{plan.price_ngn ? <span className="text-[16px] font-semibold"> /month</span> : null}
                  <div className="text-[15px] font-semibold">{renews}</div>
                </div>
                <ul className="flex flex-col gap-2 text-[14px]">
                  {plan.features.map(f => <li key={f} className="flex items-center gap-2"><RemixIcon name="ri-checkbox-circle-fill" size={17} color="#16a34a" />{f}</li>)}
                </ul>
              </>
            )}
            <button onClick={() => { setErr(''); setPicking(true) }} className="py-3 rounded-full border border-neutral-200 text-[15px] font-semibold hover:bg-neutral-50">Compare plans</button>
          </div>
        </Panel>
      </div>

      <Panel>
        <Table cols={['Invoice', 'Period', 'Amount', 'Status', '']}>
          {data?.invoices.map(i => (
            <tr key={i.id}>
              <td><div>{i.number}</div><div className="text-[12px] text-neutral-500">{i.plan}{i.kind === 'renewal' ? ' · renewal' : ''}</div></td>
              <td className="whitespace-nowrap">{shortDate(i.period_start)} – {shortDate(i.period_end)}</td>
              <td>₦{i.amount_ngn.toLocaleString('en-NG')}</td>
              <td>{i.status === 'paid' ? <Pill tone="success" dot>Paid {shortDate(i.paid_at)}</Pill> : <Pill tone="warning" dot>Due</Pill>}</td>
              <td className="text-right whitespace-nowrap">
                {i.status === 'open' && (
                  <button disabled={!!busy} onClick={() => void pay(i)} className="mr-2 px-5 py-1.5 rounded-full text-white text-[13px] font-semibold bg-[#C800DE] disabled:opacity-50">
                    {busy === i.id ? 'Opening…' : 'Pay'}
                  </button>
                )}
                <button onClick={() => void download(`${base}/invoices/${i.id}/pdf`, `${i.number}.pdf`).catch(e => setErr(apiErrorMessage(e)))}
                  className="px-5 py-1.5 rounded-full border border-neutral-200 text-[13px] font-semibold">Download</button>
              </td>
            </tr>
          ))}
          {data && !data.invoices.length && <tr><td colSpan={5} className="text-center !text-neutral-400 !py-10">No invoices yet — you’re on the free plan.</td></tr>}
        </Table>
      </Panel>

      {picking && (
        <Modal title="Choose a plan" onClose={() => setPicking(false)}>
          <p className="text-[12.5px] text-neutral-500">Billed to {org?.name}. Paid plans start a 30-day period when Bachs confirms the payment. Prices shown are placeholders.</p>
          <div className="flex flex-col gap-3">
            {plans.data?.map(p => {
              const current = p.code === plan?.code
              return (
                <div key={p.code} className={`rounded-xl border p-4 ${current ? 'border-[#C800DE] bg-brand-50' : 'border-neutral-200'}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[15px] font-bold">{p.name}</div>
                      <div className="text-[13px] text-neutral-600">{naira(p.price_ngn)}{p.price_ngn ? ' / month' : ''} · {p.limit ? `${p.limit.toLocaleString()} verifications` : 'custom volume'}</div>
                    </div>
                    {current ? <Pill tone="brand">Current</Pill> : p.price_ngn == null ? (
                      <a href="mailto:sales@foid.ng" className="px-4 py-1.5 rounded-full border border-neutral-200 text-[13px] font-semibold">Talk to us</a>
                    ) : (
                      <button disabled={!!busy} onClick={() => void choose(p.code)}
                        className="px-4 py-1.5 rounded-full text-white text-[13px] font-semibold bg-[#C800DE] disabled:opacity-50">
                        {busy === p.code ? 'Opening…' : p.price_ngn === 0 ? 'Switch' : 'Choose'}
                      </button>
                    )}
                  </div>
                  <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1 text-[12px] text-neutral-600">
                    {p.features.map(f => <li key={f}>✓ {f}</li>)}
                  </ul>
                </div>
              )
            })}
          </div>
          {err && <p className="text-[13px] text-red-500">{err}</p>}
        </Modal>
      )}
    </div>
  )
}
