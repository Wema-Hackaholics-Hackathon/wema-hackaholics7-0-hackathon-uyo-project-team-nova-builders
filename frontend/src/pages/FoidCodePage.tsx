/**
 * /c/:token — what someone sees after scanning a person's FOID code. No login.
 * Shows only first name + last initial, the credential state and yes/no checks.
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'
import { api, apiErrorMessage } from '@/lib/api'
import type { CredentialState } from '@/types/foid'

const BRAND = '#C800DE'

interface Result {
  holder: string
  code: string
  state: CredentialState
  checks: { liveness: boolean; nin: boolean; bvn: boolean; email: boolean; age_over_18: boolean | null }
  checked_at: string
}

const STATE: Record<CredentialState, { label: string; color: string; bg: string; note: string }> = {
  active:       { label: 'Active',       color: '#15803d', bg: '#dcfce7', note: 'This credential is in good standing.' },
  under_review: { label: 'Under review', color: '#a16207', bg: '#fef9c3', note: 'FOID is reviewing this credential. Treat it with care.' },
  downgraded:   { label: 'Downgraded',   color: '#c2410c', bg: '#fff7ed', note: 'Some of this credential has been downgraded.' },
  revoked:      { label: 'Revoked',      color: '#dc2626', bg: '#fee2e2', note: 'This credential is not valid. Do not rely on it.' },
}

const CHECKS: { key: keyof Result['checks']; label: string }[] = [
  { key: 'liveness',    label: 'Face (liveness) verified' },
  { key: 'nin',         label: 'NIN verified' },
  { key: 'bvn',         label: 'BVN verified' },
  { key: 'age_over_18', label: 'Over 18' },
  { key: 'email',       label: 'Email confirmed' },
]

export default function FoidCodePage() {
  const { token = '' } = useParams()
  const [res, setRes]     = useState<Result | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Result>(`/credentials/code/${encodeURIComponent(token)}`)
      .then(r => setRes(r.data))
      .catch(e => setError(apiErrorMessage(e, "This FOID code isn't valid.")))
  }, [token])

  const st = res ? STATE[res.state] : null

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col items-center px-4 py-5 sm:py-10">
      <div className="w-full max-w-[460px] bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-neutral-100" style={{ borderTop: `4px solid ${BRAND}` }}>
          <FoidWordmark height={15} color={BRAND} />
          <span className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wider">Credential check</span>
        </div>

        <div className="p-5 flex flex-col gap-4">
          {error && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-time-line" size={32} color="#a1a1aa" />
              <p className="text-[14px] text-neutral-600">{error}</p>
            </div>
          )}
          {!error && !res && (
            <div className="flex items-center justify-center gap-2 py-10 text-neutral-400 text-[13px]">
              <RemixIcon name="ri-loader-4-line" size={18} /> Checking…
            </div>
          )}
          {res && st && (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h1 className="text-[18px] font-bold text-neutral-900">{res.holder}</h1>
                  <div className="text-[12.5px] text-neutral-500 tracking-wider">{res.code}</div>
                </div>
                <span className="text-[12px] font-bold px-3 py-1 rounded-full" style={{ background: st.bg, color: st.color }}>{st.label}</span>
              </div>
              <p className="text-[13px] text-neutral-600">{st.note}</p>
              <ul className="flex flex-col divide-y divide-neutral-100 border border-neutral-100 rounded-xl">
                {CHECKS.map(c => {
                  const v = res.checks[c.key]
                  return (
                    <li key={c.key} className="flex items-center justify-between px-4 py-3 text-[13.5px]">
                      <span className="text-neutral-800">{c.label}</span>
                      {v === true && <RemixIcon name="ri-checkbox-circle-fill" size={18} color="#16a34a" />}
                      {v === false && <span className="text-neutral-400 text-[12.5px]">Not yet</span>}
                      {v === null && <span className="text-neutral-400 text-[12.5px]">Unknown</span>}
                    </li>
                  )
                })}
              </ul>
              <p className="text-[11.5px] text-neutral-400">
                Checked live with FOID at {new Date(res.checked_at).toLocaleString('en-GB')}. Ask to see a photo ID if you need to
                confirm the person in front of you is {res.holder}.
              </p>
            </>
          )}
        </div>

        <div className="px-5 py-3 bg-neutral-50 border-t border-neutral-100 flex items-center justify-center gap-1.5 text-[11.5px] text-neutral-400">
          <RemixIcon name="ri-lock-2-line" size={13} color="#a1a1aa" /> Secured by <FoidWordmark height={11} color={BRAND} />
        </div>
      </div>
    </div>
  )
}
