import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import MonoConnect from '@mono.co/connect.js'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import type { ConnectedBank, MonoTransaction } from '@/types/foid'

/* ── Mock data for unverified / preview mode ──────────────────────── */
interface MockBank {
  id: string; name: string; logo: string
  initials?: string; initialsColor?: string
  account_type: string; masked_number: string
  lastSync: string; status: 'verified' | 'error'
}

const MOCK_BANKS: MockBank[] = [
  { id: 'm1', name: 'GTBank',    logo: '/GTCO.jpg',  account_type: 'Savings',  masked_number: '•••• 4471', lastSync: 'synced 2 min ago',   status: 'verified' },
  { id: 'm2', name: 'Wema Bank', logo: '/wema.jpg',  account_type: 'Current',  masked_number: '•••• 9902', lastSync: 'synced 4 min ago',   status: 'verified' },
  { id: 'm3', name: 'Moniepoint', logo: '', initials: 'M', initialsColor: '#2563eb', account_type: 'Business', masked_number: '•••• 1130', lastSync: 'synced 1 min ago', status: 'verified' },
  { id: 'm4', name: 'Kuda Bank', logo: '/kuda.jpg',  account_type: 'Savings',  masked_number: '•••• 2287', lastSync: 'last sync failed',    status: 'error' },
]

/* ── Helpers ────────────────────────────────────────────────────────── */
function fmtSync(dt: string | null): string {
  if (!dt) return 'never synced'
  const diff = Math.floor((Date.now() - new Date(dt).getTime()) / 60_000)
  if (diff < 1) return 'just now'
  if (diff < 60) return `synced ${diff} min ago`
  return `synced ${Math.floor(diff / 60)}h ago`
}

function logoLetter(name: string) {
  return name.trim()[0]?.toUpperCase() ?? '?'
}

/* ── Avatar ─────────────────────────────────────────────────────────── */
function BankAvatar({ logo, name, initials, initialsColor }: {
  logo: string | null; name: string; initials?: string; initialsColor?: string
}) {
  const [imgError, setImgError] = useState(false)
  if (logo && !imgError) {
    return (
      <img
        src={logo}
        alt={name}
        onError={() => setImgError(true)}
        className="w-10 h-10 rounded-full object-cover border border-neutral-100 shrink-0"
      />
    )
  }
  return (
    <div
      className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-white text-[15px] font-bold"
      style={{ background: initialsColor ?? '#c026d3' }}
    >
      {initials ?? logoLetter(name)}
    </div>
  )
}

/* ── Badges ─────────────────────────────────────────────────────────── */
function VerifiedBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold whitespace-nowrap"
      style={{ background: '#fae8ff', color: '#c026d3' }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="11" fill="#c026d3" />
        <path d="M7 12.5l3.5 3.5 6-7" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Verified
    </span>
  )
}

function ErrorBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold"
      style={{ background: '#fee2e2', color: '#dc2626' }}>
      <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
      Error
    </span>
  )
}

/* ── Preview banner ─────────────────────────────────────────────────── */
function PreviewBanner() {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-amber-200 bg-amber-50 text-[13px] text-amber-800 mb-1">
      <RemixIcon name="ri-eye-line" size={16} color="#b45309" className="mt-0.5 shrink-0" />
      <p>
        <span className="font-semibold">Preview mode — </span>
        Sample data is shown below. Verify your email to connect real bank accounts via Mono Open Banking.
      </p>
    </div>
  )
}

/* ── Confirm disconnect modal ────────────────────────────────────────── */
function ConfirmDisconnect({ name, onConfirm, onCancel, loading }: {
  name: string; onConfirm: () => void; onCancel: () => void; loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-[380px] p-6 flex flex-col gap-4">
        <h2 className="text-[16px] font-bold text-neutral-900">Disconnect {name}?</h2>
        <p className="text-[13px] text-neutral-500">
          This will remove the Open Banking link. FOID will no longer be able to read transaction
          data from this account. You can reconnect at any time.
        </p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel}
            className="px-4 py-2 rounded-lg border border-neutral-200 text-[13px] font-semibold text-neutral-700 hover:bg-neutral-50">
            Cancel
          </button>
          <button onClick={onConfirm} disabled={loading}
            className="px-4 py-2 rounded-lg bg-red-500 text-white text-[13px] font-semibold hover:bg-red-600 disabled:opacity-60">
            {loading ? 'Disconnecting…' : 'Disconnect'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Add-bank modal — uses @mono.co/connect.js SDK ──────────────────── */
function AddBankModal({ onClose, onConnected }: { onClose: () => void; onConnected: () => void }) {
  const [linking, setLinking] = useState(false)
  const monoRef = useRef<MonoConnect | null>(null)

  // Keep latest callbacks in refs so the Mono instance never goes stale
  const onConnectedRef = useRef(onConnected)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onConnectedRef.current = onConnected }, [onConnected])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  // Initialise once after the modal mounts so the SDK can inject its iframe.
  // The cleanup tears down the widget div so React strict-mode double-invoke
  // doesn't leave a stale iframe behind.
  useEffect(() => {
    const instance = new MonoConnect({
      key: import.meta.env.VITE_MONO_PUBLIC_KEY as string,
      onClose: () => setLinking(false),
      onLoad: () => { /* ready */ },
      onSuccess: async ({ code }: { code: string }) => {
        setLinking(true)
        try {
          await api.post('/banks/exchange-token', { code })
          onConnectedRef.current()
          onCloseRef.current()
        } catch {
          alert('Failed to link bank account. Please try again.')
          setLinking(false)
        }
      },
    })
    instance.setup()
    monoRef.current = instance

    return () => {
      // Remove the widget div the SDK injected so a re-mount starts clean
      document.getElementById('mono-connect--widget-div')?.remove()
      monoRef.current = null
    }
  }, [])

  const handleOpen = useCallback(() => {
    monoRef.current?.open()
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-[440px] p-6 flex flex-col gap-5">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-[17px] font-bold text-neutral-900">Connect a bank account</h2>
            <p className="text-[12.5px] text-neutral-400 mt-0.5">
              Read-only Open Banking access via Mono sandbox
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-neutral-100 transition-colors shrink-0"
          >
            <RemixIcon name="ri-close-line" size={18} color="#71717a" clickable />
          </button>
        </div>

        <button
          onClick={handleOpen}
          disabled={linking}
          className="w-full py-3 rounded-xl font-bold text-white text-[14px] transition-opacity hover:opacity-90 disabled:opacity-60"
          style={{ background: 'linear-gradient(90deg, #C800DE 0%, #6C0078 100%)' }}
        >
          {linking ? 'Linking…' : 'Open Mono Connect'}
        </button>

        <div className="flex items-start gap-2 bg-neutral-50 rounded-xl px-4 py-3">
          <RemixIcon name="ri-shield-check-line" size={15} color="#a1a1aa" className="mt-0.5 shrink-0" />
          <p className="text-[11.5px] text-neutral-500 leading-relaxed">
            FOID only reads transaction data. We never store credentials or move funds.
            Connection uses the CBN-licensed Open Banking sandbox.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════
   Page
═══════════════════════════════════════════════════════════════════════ */
export default function ConnectedBankPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const isVerified = user?.email_verified ?? false

  const [banks, setBanks] = useState<ConnectedBank[]>([])
  const [loadingBanks, setLoadingBanks] = useState(false)
  const [combinedBalance, setCombinedBalance] = useState<number | null>(null)
  const [apiError, setApiError] = useState('')
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState<{ id: string; name: string } | null>(null)
  const [disconnecting, setDisconnecting] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)

  const fetchBanks = useCallback(async () => {
    if (!isVerified) return
    setLoadingBanks(true)
    setApiError('')
    try {
      const res = await api.get<ConnectedBank[]>('/banks/connected')
      const fetchedBanks = res.data
      setBanks(fetchedBanks)

      // Fetch latest transaction balance per bank and sum them
      if (fetchedBanks.length > 0) {
        const txResults = await Promise.allSettled(
          fetchedBanks.map(b =>
            api.get<MonoTransaction[]>(`/banks/${b.id}/transactions`, { params: { limit: 1 } })
          )
        )
        let total = 0
        let anyData = false
        txResults.forEach(r => {
          if (r.status === 'fulfilled' && r.value.data.length > 0) {
            total += r.value.data[0].balance / 100  // kobo → naira
            anyData = true
          }
        })
        setCombinedBalance(anyData ? total : null)
      } else {
        setCombinedBalance(null)
      }
    } catch {
      setApiError('Could not load banks. Please refresh.')
    } finally {
      setLoadingBanks(false)
    }
  }, [isVerified])

  useEffect(() => { void fetchBanks() }, [fetchBanks])

  const handleSync = async (bankId: string) => {
    setSyncingId(bankId)
    try {
      await api.post(`/banks/${bankId}/sync`)
      await fetchBanks()
    } catch {
      setApiError('Sync failed. Please try again.')
    } finally {
      setSyncingId(null)
    }
  }

  const handleDisconnect = async () => {
    if (!confirmDisconnect) return
    setDisconnecting(true)
    try {
      await api.delete(`/banks/${confirmDisconnect.id}`)
      setBanks(prev => prev.filter(b => b.id !== confirmDisconnect.id))
      setConfirmDisconnect(null)
    } catch {
      setApiError('Disconnect failed. Please try again.')
    } finally {
      setDisconnecting(false)
    }
  }

  const connectedCount = isVerified ? banks.length : MOCK_BANKS.length
  const errorCount = isVerified
    ? banks.filter(b => b.status === 'error').length
    : MOCK_BANKS.filter(b => b.status === 'error').length

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Connected Bank Accounts</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">
            Manage the banks and fintechs linked to your FOID identity via Open Banking
          </p>
        </div>
        <button
          onClick={isVerified ? () => setShowAddModal(true) : undefined}
          disabled={!isVerified}
          title={!isVerified ? 'Verify your email to connect banks' : undefined}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full font-semibold text-[14px] text-white transition-opacity hover:opacity-90 shrink-0 self-start disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: '#c026d3' }}
        >
          <RemixIcon name="ri-add-line" size={18} color="#fff" clickable />
          Connect Bank
        </button>
      </div>

      {/* Preview banner for unverified */}
      {!isVerified && <PreviewBanner />}

      {/* API error */}
      {apiError && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-[13px] text-red-700">
          <RemixIcon name="ri-error-warning-line" size={15} color="#dc2626" />
          {apiError}
          <button onClick={() => setApiError('')} className="ml-auto text-red-400 hover:text-red-600">
            <RemixIcon name="ri-close-line" size={14} clickable />
          </button>
        </div>
      )}

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Connected Banks" value={String(connectedCount)}
          sub="Open Banking linked accounts" subColor="text-brand-500 font-semibold" icon="ri-bank-line" />
        <StatCard
          label="Combined Balance"
          value={
            loadingBanks
              ? '…'
              : combinedBalance !== null
                ? `₦${combinedBalance.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '₦—'
          }
          sub="Latest balance across linked accounts" subColor="text-neutral-400" icon="ri-coin-line" />
        <StatCard
          label="Last Synced"
          value={isVerified && banks.length > 0 ? fmtSync(banks[0].last_synced_at) : '—'}
          sub="Auto-sync every 15 min" subColor="text-neutral-400" icon="ri-refresh-line" />
        <StatCard label="Needs Attention" value={String(errorCount)}
          sub={errorCount > 0 ? 'Reconnect required' : 'All connections healthy'}
          subColor={errorCount > 0 ? 'text-red-500 font-semibold' : 'text-neutral-400'}
          icon="ri-alarm-warning-fill" />
      </div>

      {/* ── Bank list table ── */}
      <div className="bg-white border border-neutral-200 rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <span className="text-[15px] font-bold text-neutral-900">Your linked institutions</span>
          <span className="text-[12px] text-neutral-400 hidden sm:block">
            Data is shared read-only and only with your consent
          </span>
        </div>

        {/* Loading */}
        {isVerified && loadingBanks && (
          <div className="px-6 py-10 text-center text-[13px] text-neutral-400">
            <RemixIcon name="ri-loader-4-line" size={20} color="#a1a1aa" className="mx-auto mb-2 animate-spin" />
            Loading your banks…
          </div>
        )}

        {/* Real bank rows */}
        {isVerified && !loadingBanks && banks.map(bank => (
          <div key={bank.id}
            className="flex items-center justify-between px-6 py-4 hover:bg-neutral-50/60 transition-colors border-b border-neutral-100 last:border-b-0">
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <BankAvatar logo={bank.logo_url} name={bank.name} />
              <div className="min-w-0">
                <div className="text-[14px] font-bold text-neutral-900 leading-tight">{bank.name}</div>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  {bank.masked_number && (
                    <span className="text-[12px] text-neutral-400 font-mono">{bank.masked_number}</span>
                  )}
                  {bank.account_type && (
                    <><span className="text-neutral-300 text-[11px]">·</span>
                      <span className="text-[12px] text-neutral-400">{bank.account_type}</span></>
                  )}
                  <span className="text-neutral-300 text-[11px]">·</span>
                  <span className="text-[12px]"
                    style={{ color: bank.status === 'error' ? '#ef4444' : '#a1a1aa' }}>
                    {fmtSync(bank.last_synced_at)}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              {bank.status === 'error' ? <ErrorBadge /> : <VerifiedBadge />}
              <button
                onClick={() => navigate(`/dashboard/banks/${bank.id}/transactions`)}
                className="px-3 py-1.5 rounded-full border border-neutral-200 text-[12px] font-semibold text-neutral-700 hover:bg-neutral-50 hover:border-neutral-300 transition-colors whitespace-nowrap"
              >
                Transactions
              </button>
              <button onClick={() => void handleSync(bank.id)} disabled={syncingId === bank.id}
                title="Sync now"
                className="p-1.5 rounded-full hover:bg-neutral-100 transition-colors disabled:opacity-50">
                <RemixIcon name="ri-refresh-line" size={15} color="#71717a" clickable
                  className={syncingId === bank.id ? 'animate-spin' : ''} />
              </button>
              <button onClick={() => setConfirmDisconnect({ id: bank.id, name: bank.name })}
                className="px-3 py-1.5 rounded-full border border-neutral-200 text-[12px] font-semibold text-neutral-700 hover:bg-neutral-50 hover:border-neutral-300 transition-colors whitespace-nowrap">
                Disconnect
              </button>
            </div>
          </div>
        ))}

        {/* Mock rows (preview mode) */}
        {!isVerified && MOCK_BANKS.map(bank => (
          <div key={bank.id}
            className="flex items-center justify-between px-6 py-4 hover:bg-neutral-50/60 transition-colors border-b border-neutral-100 last:border-b-0 opacity-80">
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <BankAvatar logo={bank.logo || null} name={bank.name} initials={bank.initials} initialsColor={bank.initialsColor} />
              <div className="min-w-0">
                <div className="text-[14px] font-bold text-neutral-900 leading-tight">{bank.name}</div>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  <span className="text-[12px] text-neutral-400 font-mono">{bank.masked_number}</span>
                  <span className="text-neutral-300 text-[11px]">·</span>
                  <span className="text-[12px] text-neutral-400">{bank.account_type}</span>
                  <span className="text-neutral-300 text-[11px]">·</span>
                  <span className="text-[12px]"
                    style={{ color: bank.lastSync.includes('failed') ? '#ef4444' : '#a1a1aa' }}>
                    {bank.lastSync}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              {bank.status === 'error' ? <ErrorBadge /> : <VerifiedBadge />}
              <span className="text-[12px] text-neutral-300 italic hidden sm:block">preview</span>
            </div>
          </div>
        ))}

        {/* Empty state */}
        {isVerified && !loadingBanks && banks.length === 0 && (
          <div className="px-6 py-12 text-center flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-neutral-100 flex items-center justify-center">
              <RemixIcon name="ri-bank-line" size={22} color="#a1a1aa" />
            </div>
            <p className="text-[14px] font-semibold text-neutral-700">No banks connected yet</p>
            <p className="text-[13px] text-neutral-400 max-w-xs">
              Click <strong>Connect Bank</strong> above to link your first account via Mono Open Banking.
            </p>
          </div>
        )}
      </div>

      {/* Disconnect confirm modal */}
      {confirmDisconnect && (
        <ConfirmDisconnect
          name={confirmDisconnect.name}
          onConfirm={() => void handleDisconnect()}
          onCancel={() => setConfirmDisconnect(null)}
          loading={disconnecting}
        />
      )}

      {/* Add bank modal — Mono Connect npm package */}
      {showAddModal && (
        <AddBankModal
          onClose={() => setShowAddModal(false)}
          onConnected={fetchBanks}
        />
      )}
    </div>
  )
}
