import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RemixIcon from '@/components/RemixIcon'
import StatCard from '@/components/StatCard'
import SegmentedTabs from '@/components/SegmentedTabs'
import { useCredential } from '@/contexts/CredentialContext'
import { api, apiErrorMessage } from '@/lib/api'
import type { ConnectedApp, CredentialState } from '@/types/foid'


/* ── Types ──────────────────────────────────────────────────────────── */
type CredentialStatus = 'active' | 'expiring' | 'revoked'

interface Credential {
  id: string
  orgId?: string          // set for businesses; the FOID master credential has none
  label?: string          // badge text override (e.g. "Under Review")
  platform: string
  logo: string
  scope: string
  issued: string
  expires: string | null
  status: CredentialStatus
}

/* ── Real data: one credential per business you've shared with (GET /connected-apps) ── */
const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

/** foid_cr_8x291a…e7d40 — a readable short form of the consent grant id */
function shortId(id: string): string {
  const hex = id.replace(/-/g, '')
  return `foid_cr_${hex.slice(0, 6)}…${hex.slice(-5)}`
}

function toCredential(app: ConnectedApp): Credential {
  const first = app.grants[0]
  return {
    id: first ? shortId(first.id) : '—',
    orgId: app.org_id,
    platform: app.sandbox ? `${app.name} (sandbox)` : app.name,
    logo: app.logo_url ?? '/logo.png',
    scope: app.scopes.map(s => s.scope.charAt(0).toUpperCase() + s.scope.slice(1)).join(' · ')
      || app.checks.map(c => c.type.toUpperCase()).join(' · ') || 'Identity checks',
    issued: fmtDate(app.first_connected_at),
    expires: null,
    status: app.status === 'active' ? 'active' : 'revoked',
  }
}

/* ── Status badge ───────────────────────────────────────────────────── */
const STATUS_META: Record<CredentialStatus, { label: string; bg: string; color: string }> = {
  active:   { label: 'Active',   bg: '#dcfce7', color: '#15803d' },
  expiring: { label: 'Expiring', bg: '#fff7ed', color: '#c2410c' },
  revoked:  { label: 'Revoked',  bg: '#fee2e2', color: '#dc2626' },
}

function StatusBadge({ status, label }: { status: CredentialStatus; label?: string }) {
  const m = STATUS_META[status]
  return (
    <span
      className="inline-flex items-center px-3 py-1 rounded-full text-[12px] font-semibold"
      style={{ background: m.bg, color: m.color }}
    >
      {label ?? m.label}
    </span>
  )
}

/* ── Action button ──────────────────────────────────────────────────── */
function ActionButton({ cred, onRevoke, onOpen }: { cred: Credential; onRevoke: () => void; onOpen: () => void }) {
  const master   = !cred.orgId
  const label    = master ? 'View' : cred.status === 'revoked' ? 'Revoked' : 'Revoke'
  const disabled = !master && cred.status === 'revoked'
  return (
    <button
      disabled={disabled}
      onClick={master ? onOpen : onRevoke}
      className="px-4 py-1.5 rounded-full border border-neutral-200 text-[12px] font-semibold text-neutral-700 hover:bg-neutral-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {label}
    </button>
  )
}

/* ── Filter tabs ────────────────────────────────────────────────────── */
type Filter = 'all' | 'active' | 'expiring' | 'revoked'

const TABS: { key: Filter; label: string }[] = [
  { key: 'all',      label: 'All'      },
  { key: 'active',   label: 'Active'   },
  { key: 'expiring', label: 'Expiring' },
  { key: 'revoked',  label: 'Revoked'  },
]

/* ── FOID credential state → CredentialStatus mapping ────────────────── */
const FOID_STATE_TO_STATUS: Record<CredentialState, CredentialStatus> = {
  active:       'active',
  under_review: 'expiring',
  downgraded:   'expiring',
  revoked:      'revoked',
}

const FOID_STATE_LABELS: Record<CredentialState, string> = {
  active:       'Active',
  under_review: 'Under Review',
  downgraded:   'Downgraded',
  revoked:      'Revoked',
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function VerificationCredentialsPage() {
  const { credential } = useCredential()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [apps, setApps] = useState<Credential[] | null>(null)   // null = loading
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)

  const load = useCallback(async () => {
    try {
      setApps((await api.get<ConnectedApp[]>('/connected-apps')).data.map(toCredential))
      setError('')
    } catch (e) {
      setApps([])
      setError(apiErrorMessage(e, 'Could not load where your credential is shared.'))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function revoke(cred: Credential) {
    if (!cred.orgId) return
    if (!window.confirm(`Revoke ${cred.platform}'s access? They will stop receiving any of your data.`)) return
    try {
      await api.delete(`/connected-apps/${cred.orgId}`)
      await load()
    } catch (e) {
      window.alert(apiErrorMessage(e, 'Could not revoke access. Please try again.'))
    }
  }

  async function downloadSummary() {
    setDownloading(true)
    try {
      const res = await api.get<Blob>('/auth/me/identity-summary', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'FOID_Identity_Summary.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      window.alert(apiErrorMessage(e, 'Could not download your identity summary.'))
    } finally {
      setDownloading(false)
    }
  }

  /* Inject the live FOID master credential as the first row */
  const foidEntry: Credential = {
    id: credential.id,
    platform: 'FOID Master Credential',
    logo: '/logo.png',
    scope: 'identity_verified · bvn_validated · age_over_18 · income_band · account_stability',
    issued: new Date(credential.issued_at).toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' }),
    expires: null,
    status: FOID_STATE_TO_STATUS[credential.state],
    label: FOID_STATE_LABELS[credential.state],
  }

  const shared = apps ?? []
  const allCredentials = credential.id ? [foidEntry, ...shared] : shared
  const count = (st: CredentialStatus) => allCredentials.filter(c => c.status === st).length
  const activeApps = shared.filter(c => c.status === 'active').length

  const visible = allCredentials.filter(c => {
    if (filter !== 'all' && c.status !== filter) return false
    if (search && !c.platform.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-[22px] md:text-[26px] font-bold tracking-tight text-neutral-900">Verification Credentials</h1>
          <p className="text-neutral-500 mt-1 text-[13.5px]">Every credential generated from your FOID identity, and where it's been shared</p>
        </div>
        <button onClick={() => void downloadSummary()} disabled={downloading}
          className="flex items-center gap-2 px-5 py-2.5 border border-neutral-200 rounded-full font-semibold text-[14px] text-neutral-800 bg-white hover:bg-neutral-50 transition-colors shrink-0 self-start disabled:opacity-60">
          <RemixIcon name="ri-download-2-line" size={20} /> {downloading ? 'Preparing…' : 'Download Identity Summary'}
        </button>
      </div>

      {/* ── Live FOID credential state banner ── */}
      {credential.state !== 'active' && (
        <div
          className="flex items-center gap-3 px-5 py-3 rounded-xl border text-[13px] font-semibold"
          style={{
            background: credential.state === 'revoked' ? '#fee2e2' : '#fef9c3',
            borderColor: credential.state === 'revoked' ? '#fca5a5' : '#fde68a',
            color: credential.state === 'revoked' ? '#dc2626' : '#a16207',
          }}
        >
          <RemixIcon name="ri-alert-fill" size={16} color={credential.state === 'revoked' ? '#dc2626' : '#a16207'} />
          <span>
            Your FOID master credential is currently <strong>{FOID_STATE_LABELS[credential.state]}</strong>.
            {credential.state === 'under_review' && ' Relying parties may see reduced access until review is complete.'}
            {credential.state === 'downgraded' && ' Some claims have been downgraded — new credential requests may be limited.'}
            {credential.state === 'revoked' && ' All credential sharing has been halted. Contact support or re-verify your identity.'}
          </span>
        </div>
      )}

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Credentials" value={apps === null ? '…' : String(count('active'))}
          sub={activeApps ? `Shared with ${activeApps} business${activeApps === 1 ? '' : 'es'}` : 'Not shared with any business yet'}
          subColor="text-neutral-400" icon="ri-file-text-fill" />
        <StatCard label="Shared With" value={apps === null ? '…' : `${activeApps} app${activeApps === 1 ? '' : 's'}`}
          sub="Businesses that can see your data" subColor="text-neutral-400" icon="ri-user-shared-2-fill" />
        <StatCard label="Expiring Soon" value={apps === null ? '…' : String(count('expiring'))}
          sub="Shares don't expire until you revoke them" subColor="text-neutral-400" icon="ri-alarm-warning-fill" />
        <StatCard label="Revoked" value={apps === null ? '…' : String(count('revoked'))}
          sub="Access removed" subColor="text-neutral-400" icon="ri-close-circle-fill" />
      </div>

      {/* ── Table card ── */}
      <div className="bg-white rounded-2xl overflow-hidden">

        {/* Toolbar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 py-4">
          {/* Sliding-pill segmented control */}
          <div className="overflow-x-auto w-full sm:w-auto">
            <SegmentedTabs value={filter} onChange={setFilter} tabs={TABS} />
          </div>

          {/* Search */}
          <div className="sm:ml-auto relative w-full sm:w-[280px]">
            <RemixIcon
              name="ri-search-line"
              size={16}
              color="#a1a1aa"
              className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by platform"
              className="pl-8 pr-4 py-2 w-full rounded-full border border-neutral-200 bg-neutral-50 text-[13px] text-neutral-800 placeholder:text-neutral-400 focus:outline-none focus:border-brand-400"
            />
          </div>
        </div>

        {/* Table — horizontally scrollable on mobile */}
        <div className="overflow-x-auto">
        <table className="w-full text-left text-[16px] border-collapse min-w-[700px]">
          <thead>
            <tr className="bg-neutral-200">
              {['CREDENTIAL ID', 'SHARED WITH', 'SCOPE', 'ISSUED', 'EXPIRES', 'STATUS', 'ACTIONS'].map((col, i, arr) => (
                <th
                  key={col}
                  className={[
                    'px-6 py-4 text-[16px] font-semibold text-black uppercase tracking-widest whitespace-nowrap',
                    i === 0             ? 'rounded-tl-xl' : '',
                    i === arr.length - 1 ? 'rounded-tr-xl' : '',
                  ].join(' ')}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((cred, i) => (
              <tr key={i} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/60 transition-colors">
                {/* Credential ID */}
                <td className="px-6 py-5 text-black">{cred.id}</td>

                {/* Shared with — bank logo + name */}
                <td className="px-6 py-5">
                  <div className="flex items-center gap-3">
                    <img
                      src={cred.logo}
                      alt={cred.platform}
                      className="w-9 h-9 rounded-lg object-contain shrink-0 border border-neutral-100 bg-white p-0.5"
                    />
                    <span className="font-semibold text-neutral-900 whitespace-nowrap">{cred.platform}</span>
                  </div>
                </td>

                {/* Scope */}
                <td className="px-6 py-5 text-neutral-600 max-w-[160px]">{cred.scope}</td>

                {/* Issued */}
                <td className="px-6 py-5 text-neutral-500 whitespace-nowrap">{cred.issued}</td>

                {/* Expires */}
                <td className="px-6 py-5   text-neutral-500 whitespace-nowrap">{cred.expires ?? '—'}</td>

                {/* Status */}
                <td className="px-6 py-5"><StatusBadge status={cred.status} label={cred.label} /></td>

                {/* Actions */}
                <td className="px-6 py-5">
                  <ActionButton cred={cred} onRevoke={() => void revoke(cred)} onOpen={() => navigate('/dashboard/identity')} />
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-neutral-400">
                  {apps === null ? 'Loading…' : error || (allCredentials.length === 0
                    ? "You haven't shared your FOID credential with any business yet."
                    : 'No credentials match your filter.')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

    </div>
  )
}
