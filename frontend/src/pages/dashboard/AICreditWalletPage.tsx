import { useCallback, useEffect, useState } from 'react'
import StatCard from '@/components/StatCard'
import RemixIcon from '@/components/RemixIcon'
import { api } from '@/lib/api'

/* ── Types from backend ──────────────────────────────────────────────── */
interface WalletTx {
  id: string
  transaction_type: string   // 'usage' | 'purchase'
  credits_delta: number
  feature: string
  status: string | null
  created_at: string
}
interface WalletData {
  id: string
  free_credits: number
  paid_credits: number
  balance: number
  auto_topup_threshold: number | null
  updated_at: string
  transactions: WalletTx[]
}

/* ── Credit top-up presets ──────────────────────────────────────────── */
const TOPUP_PRESETS = [
  { label: '100 credits',   amount_ngn: 500,    display: '₦500'    },
  { label: '500 credits',   amount_ngn: 2500,   display: '₦2,500'  },
  { label: '1,000 credits', amount_ngn: 5000,   display: '₦5,000'  },
  { label: '5,000 credits', amount_ngn: 25000,  display: '₦25,000' },
]

const PURPLE = '#9b00d9'

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
export default function AiCreditWallet() {
  const [wallet, setWallet]         = useState<WalletData | null>(null)
  const [loading, setLoading]       = useState(true)

  // ── Buy-credits modal state ──────────────────────────────────────────
  const [showBuy, setShowBuy]       = useState(false)
  const [selectedIdx, setSelected]  = useState(1)
  const [customAmt, setCustomAmt]   = useState('')
  const [showCustom, setShowCustom] = useState(false)
  const [buying, setBuying]         = useState(false)
  const [buyError, setBuyError]     = useState<string | null>(null)

  // ── Auto top-up modal state ──────────────────────────────────────────
  const [showAutoTopup, setShowAutoTopup] = useState(false)
  const [autoThreshold, setAutoThreshold] = useState('')
  const [savingAuto, setSavingAuto]       = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<WalletData>('/wallet')
      setWallet(res.data)
      if (res.data.auto_topup_threshold !== null) {
        setAutoThreshold(String(res.data.auto_topup_threshold))
      }
    } catch { /* unverified — leave null */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  // ── Derived stats ────────────────────────────────────────────────────
  const txs = wallet?.transactions ?? []
  const now  = new Date()
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

  const usedThisMonth = txs
    .filter(t => t.transaction_type === 'usage' && t.created_at.startsWith(currentMonth))
    .reduce((s, t) => s + Math.abs(t.credits_delta), 0)

  const purchasedThisMonth = txs
    .filter(t => t.transaction_type === 'purchase' && t.status === 'paid' && t.created_at.startsWith(currentMonth))
    .reduce((s, t) => s + t.credits_delta, 0)

  const last30 = txs
    .filter(t => t.transaction_type === 'usage')
    .slice(0, 30)
  const avgDaily = last30.length > 0
    ? Math.round(last30.reduce((s, t) => s + Math.abs(t.credits_delta), 0) / 30)
    : 0

  const lastPurchase = txs.find(t => t.transaction_type === 'purchase' && t.status === 'paid')
  const lastPurchaseDate = lastPurchase
    ? new Date(lastPurchase.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
    : '—'

  // ── Purchase handler ─────────────────────────────────────────────────
  const handleBuy = async () => {
    setBuyError(null)
    const amount = showCustom ? parseInt(customAmt, 10) : TOPUP_PRESETS[selectedIdx].amount_ngn
    if (!amount || amount < 500) { setBuyError('Minimum purchase is ₦500'); return }
    setBuying(true)
    try {
      const res = await api.post<{ authorization_url: string }>('/wallet/initiate-purchase', { amount_ngn: amount })
      window.location.href = res.data.authorization_url
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setBuyError(e.response?.data?.detail ?? 'Failed to start checkout. Please try again.')
      setBuying(false)
    }
  }

  // ── Auto top-up handler ──────────────────────────────────────────────
  const handleSaveAutoTopup = async () => {
    setSavingAuto(true)
    try {
      const threshold = autoThreshold ? parseInt(autoThreshold, 10) : null
      const res = await api.post<WalletData>('/wallet/auto-topup', { threshold })
      setWallet(prev => prev ? { ...prev, auto_topup_threshold: res.data.auto_topup_threshold } : prev)
      setShowAutoTopup(false)
    } catch { /* silently fail */ }
    finally { setSavingAuto(false) }
  }

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">AI Credit Wallet</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            No subscriptions — pay-as-you-go credits for AI-powered features
          </p>
        </div>
        <button
          onClick={() => setShowBuy(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-white rounded-full font-semibold text-[14px] transition-colors shrink-0 w-full sm:w-auto justify-center"
        >
          <RemixIcon name="ri-add-circle-line" size={18} color="#fff" />
          Buy Credits
        </button>
      </div>

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Current Balance"
          value={loading ? '…' : wallet?.balance.toLocaleString() ?? '0'}
          sub={wallet && wallet.balance > 0 ? `~${Math.floor(wallet.balance / 1)} msgs remaining` : 'Top up to get started'}
          subColor="text-neutral-400" icon="ri-quill-pen-fill" />
        <StatCard
          label="Used This Month"
          value={loading ? '…' : usedThisMonth.toLocaleString()}
          sub={usedThisMonth > 0 ? 'Across AI chat & receipt scans' : 'No usage yet this month'}
          subColor="text-neutral-400" icon="ri-flashlight-fill" />
        <StatCard
          label="Purchased This Month"
          value={loading ? '…' : purchasedThisMonth.toLocaleString()}
          sub={purchasedThisMonth > 0 ? `Last purchase: ${lastPurchaseDate}` : 'No purchases this month'}
          subColor="text-neutral-400" icon="ri-handbag-fill" />
        <StatCard
          label="Avg. Daily Usage"
          value={loading ? '…' : (avgDaily > 0 ? `${avgDaily} cr` : '0 cr')}
          sub="Last 30 transactions"
          subColor="text-neutral-400" icon="ri-bar-chart-fill" />
      </div>

      {/* ── Balance card + recent usage ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Balance card column */}
        <div className="flex flex-col justify-between gap-3">
          <div className="rounded-3xl p-4">
            <div className="rounded-2xl p-8 text-white flex flex-col gap-4 min-h-[250px] relative overflow-hidden"
              style={{ background: 'linear-gradient(90deg, #8A0194 0%, #2B002E 100%)' }}>
              {/* background texture */}
              <img src="/card-back.png" aria-hidden="true"
                className="absolute inset-0 w-full h-full object-cover opacity-20 pointer-events-none select-none" />

              {/* Top row */}
              <div className="relative flex items-start justify-between">
                <div>
                  <div className="text-[28px] font-extrabold leading-none tracking-tight">
                    {loading ? '…' : `${(wallet?.balance ?? 0).toLocaleString()} credits`}
                  </div>
                  {wallet && (
                    <div className="text-[12px] opacity-60 mt-1">
                      {wallet.free_credits.toLocaleString()} free · {wallet.paid_credits.toLocaleString()} paid
                    </div>
                  )}
                </div>
                <span className="px-3 py-1 rounded-full text-[11px] font-bold shrink-0"
                  style={{ background: (wallet?.balance ?? 0) > 0 ? 'rgba(255,255,255,0.2)' : 'rgba(255,100,100,0.4)' }}>
                  {(wallet?.balance ?? 0) > 0 ? 'Active' : 'Empty'}
                </span>
              </div>

              {/* Bottom row */}
              <div className="relative flex items-end justify-between mt-auto">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] uppercase tracking-widest opacity-60">Auto Top-Up</span>
                  <span className="text-[13px] font-semibold">
                    {wallet?.auto_topup_threshold ? `At ${wallet.auto_topup_threshold.toLocaleString()} credits` : 'Disabled'}
                  </span>
                </div>
                <div className="flex flex-col items-end gap-0.5">
                  <span className="text-[10px] uppercase tracking-widest opacity-60">Last Purchase</span>
                  <span className="text-[13px] font-semibold">{lastPurchaseDate}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <img src="/logo.png" alt="FOID" className="h-9 w-auto object-contain" />
                  <span style={{ fontWeight: 800, fontSize: 24, letterSpacing: '-0.4px', color: '#fff' }}>Foid</span>
                </div>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button onClick={() => setShowBuy(true)}
              className="flex-1 py-2.5 rounded-full text-[13px] font-bold border border-neutral-200 bg-white hover:bg-neutral-50 transition-colors text-neutral-900 flex items-center justify-center gap-2">
              <RemixIcon name="ri-add-circle-line" size={16} color="#18181b" />
              Buy Credits
            </button>
            <button onClick={() => setShowAutoTopup(true)}
              className="flex-1 py-2.5 rounded-full text-[13px] font-bold border border-neutral-200 bg-white hover:bg-neutral-50 transition-colors text-neutral-900 flex items-center justify-center gap-2">
              <RemixIcon name="ri-refresh-line" size={16} color="#18181b" />
              Auto Top-up
            </button>
          </div>
        </div>

        {/* Recent usage table */}
        <div className="bg-white border border-neutral-200 rounded-2xl p-5">
          <div className="font-bold text-[15px] text-neutral-900 mb-4">Recent usage</div>
          {loading ? (
            <div className="py-10 text-center text-[13px] text-neutral-400">Loading…</div>
          ) : txs.filter(t => t.transaction_type === 'usage').length === 0 ? (
            <div className="py-10 text-center">
              <RemixIcon name="ri-flashlight-line" size={32} color="#d4d4d8" />
              <p className="text-[13px] text-neutral-400 mt-2">No usage yet — start chatting or scan a receipt</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse min-w-[380px]">
                <thead>
                  <tr className="border-b border-neutral-100">
                    {['DATE', 'FEATURE', 'CREDITS'].map(col => (
                      <th key={col} className="pb-3 text-[11px] font-bold text-neutral-400 uppercase tracking-widest whitespace-nowrap px-2 last:text-right">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {txs.filter(t => t.transaction_type === 'usage').slice(0, 10).map(row => (
                    <tr key={row.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/60 transition-colors">
                      <td className="py-4 px-2 text-[12px] text-neutral-500 whitespace-nowrap">
                        {fmtDate(row.created_at)}
                      </td>
                      <td className="py-4 px-2 text-[13px] text-neutral-900 max-w-[180px] truncate">{row.feature}</td>
                      <td className="py-4 px-2 text-[13px] font-bold text-right" style={{ color: '#dc2626' }}>
                        {row.credits_delta}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ── Purchase history ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-5 border-b border-neutral-100">
          <div className="font-bold text-[15px] text-neutral-900">Purchase history</div>
        </div>
        {loading ? (
          <div className="py-10 text-center text-[13px] text-neutral-400">Loading…</div>
        ) : txs.filter(t => t.transaction_type === 'purchase').length === 0 ? (
          <div className="py-10 text-center">
            <RemixIcon name="ri-handbag-line" size={32} color="#d4d4d8" />
            <p className="text-[13px] text-neutral-400 mt-2">No purchases yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-neutral-100">
                  {['DATE', 'DESCRIPTION', 'CREDITS', 'STATUS'].map(col => (
                    <th key={col} className="px-6 py-4 text-[11px] font-bold text-neutral-400 uppercase tracking-widest whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {txs.filter(t => t.transaction_type === 'purchase').map(row => (
                  <tr key={row.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/60 transition-colors">
                    <td className="px-6 py-4 text-[13px] text-neutral-500 whitespace-nowrap">{fmtDate(row.created_at)}</td>
                    <td className="px-6 py-4 text-[13px] font-semibold text-neutral-900 max-w-[260px] truncate">{row.feature}</td>
                    <td className="px-6 py-4 text-[13px] font-bold text-green-600">+{row.credits_delta.toLocaleString()}</td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-[11px] font-bold ${row.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                        {row.status === 'paid' ? 'Paid' : 'Pending'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ══════════════════════════════════════════════════════════════
          BUY CREDITS MODAL
      ════════════════════════════════════════════════════════════════ */}
      {showBuy && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.45)' }}
          onClick={e => { if (e.target === e.currentTarget) setShowBuy(false) }}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 flex flex-col gap-5">

            {/* Modal header */}
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[18px] font-bold text-neutral-900">Buy AI Credits</div>
                <div className="text-[13px] text-neutral-400 mt-0.5">₦5 per credit · no subscription · never expire</div>
              </div>
              <button onClick={() => setShowBuy(false)}
                className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-neutral-100 transition-colors">
                <RemixIcon name="ri-close-line" size={18} color="#71717a" />
              </button>
            </div>

            {/* Current balance */}
            {wallet && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl" style={{ background: '#fdf4ff' }}>
                <RemixIcon name="ri-quill-pen-fill" size={20} color={PURPLE} />
                <span className="text-[13px] font-semibold text-neutral-900">
                  Current balance: <span style={{ color: PURPLE }}>{wallet.balance.toLocaleString()} credits</span>
                </span>
              </div>
            )}

            {/* Preset grid */}
            <div className="grid grid-cols-2 gap-3">
              {TOPUP_PRESETS.map((p, i) => (
                <button key={i}
                  onClick={() => { setSelected(i); setShowCustom(false) }}
                  className="flex flex-col items-start px-4 py-3 rounded-xl border text-left transition-all"
                  style={{
                    border: !showCustom && selectedIdx === i ? `2px solid ${PURPLE}` : '1.5px solid #e4e4e7',
                    background: !showCustom && selectedIdx === i ? '#fdf4ff' : '#fff',
                  }}>
                  <span className="text-[14px] font-bold text-neutral-900">{p.label}</span>
                  <span className="text-[12px] text-neutral-400">{p.display}</span>
                </button>
              ))}
            </div>

            {/* Custom amount */}
            <button onClick={() => setShowCustom(v => !v)}
              className="text-[13px] font-semibold text-left transition-colors"
              style={{ color: PURPLE }}>
              {showCustom ? '← Use preset amount' : 'Enter a custom amount →'}
            </button>

            {showCustom && (
              <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-neutral-200 bg-neutral-50">
                <span className="text-[14px] text-neutral-400 shrink-0">₦</span>
                <input type="number" value={customAmt} onChange={e => setCustomAmt(e.target.value)}
                  placeholder="e.g. 10000" min={500}
                  className="flex-1 bg-transparent text-[14px] text-neutral-800 focus:outline-none" />
                {customAmt && parseInt(customAmt, 10) >= 500 && (
                  <span className="text-[12px] text-neutral-400 shrink-0">
                    = {Math.floor(parseInt(customAmt, 10) / 5).toLocaleString()} credits
                  </span>
                )}
              </div>
            )}

            {buyError && <p className="text-[13px] text-red-500">{buyError}</p>}

            {/* Action buttons */}
            <div className="flex gap-3 pt-1">
              <button onClick={() => setShowBuy(false)}
                className="flex-1 py-3 rounded-full text-[14px] font-semibold border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors">
                Cancel
              </button>
              <button onClick={handleBuy} disabled={buying}
                className="flex-1 py-3 rounded-full text-[14px] font-bold text-white transition-opacity disabled:opacity-60"
                style={{ background: PURPLE }}>
                {buying ? 'Opening checkout…'
                  : showCustom && customAmt && parseInt(customAmt, 10) >= 500
                    ? `Buy ${Math.floor(parseInt(customAmt, 10) / 5).toLocaleString()} credits`
                    : `Buy ${TOPUP_PRESETS[selectedIdx].label}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════
          AUTO TOP-UP MODAL
      ════════════════════════════════════════════════════════════════ */}
      {showAutoTopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.45)' }}
          onClick={e => { if (e.target === e.currentTarget) setShowAutoTopup(false) }}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-5">

            <div className="flex items-center justify-between">
              <div>
                <div className="text-[18px] font-bold text-neutral-900">Auto Top-up</div>
                <div className="text-[13px] text-neutral-400 mt-0.5">Automatically buy credits when balance drops below a threshold</div>
              </div>
              <button onClick={() => setShowAutoTopup(false)}
                className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-neutral-100 transition-colors">
                <RemixIcon name="ri-close-line" size={18} color="#71717a" />
              </button>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-[13px] font-semibold text-neutral-700">
                Top up when balance falls below (credits)
              </label>
              <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-neutral-200 bg-neutral-50">
                <input type="number" value={autoThreshold} onChange={e => setAutoThreshold(e.target.value)}
                  placeholder="e.g. 50  (leave blank to disable)"
                  className="flex-1 bg-transparent text-[14px] text-neutral-800 focus:outline-none" />
              </div>
              <p className="text-[12px] text-neutral-400">
                Leave blank to disable auto top-up. When triggered, 500 credits (₦2,500) will be purchased automatically.
              </p>
            </div>

            <div className="flex gap-3">
              <button onClick={() => setShowAutoTopup(false)}
                className="flex-1 py-3 rounded-full text-[14px] font-semibold border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors">
                Cancel
              </button>
              <button onClick={handleSaveAutoTopup} disabled={savingAuto}
                className="flex-1 py-3 rounded-full text-[14px] font-bold text-white transition-opacity disabled:opacity-60"
                style={{ background: PURPLE }}>
                {savingAuto ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
