/**
 * /liveness/:token — the phone side of "Continue on my phone". No login: the single-use,
 * 10-minute link is the key. Shows whose check it is, runs the same camera stage, then
 * tells the person to go back to their other device (which updates by itself).
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'
import { api, apiErrorMessage } from '@/lib/api'
import LivenessStage, { type LivenessResult, type StartedSession } from './LivenessStage'

const BRAND = '#C800DE'

interface Info { status: string; purpose: string; seconds_left: number; display_name: string }

function mmss(s: number) { return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }

export default function LivenessHandoffPage() {
  const { token = '' } = useParams()
  const base = `/liveness/handoff/${token}`
  const [info, setInfo]     = useState<Info | null>(null)
  const [fatal, setFatal]   = useState('')
  const [left, setLeft]     = useState(0)
  const [result, setResult] = useState<LivenessResult | null>(null)

  const load = useCallback(async () => {
    try {
      const i = (await api.get<Info>(base)).data
      setInfo(i)
      setLeft(i.seconds_left)
    } catch (e) {
      setFatal(apiErrorMessage(e, 'This link is invalid.'))
    }
  }, [base])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = setInterval(() => setLeft(l => Math.max(0, l - 1)), 1000)
    return () => clearInterval(t)
  }, [])

  const unusable = info && (info.status === 'expired' || info.status === 'completed' || info.status === 'cancelled' || left <= 0)
  const start = async (): Promise<StartedSession> => (await api.post<StartedSession>(`${base}/start`)).data
  const complete = async (sid: string): Promise<LivenessResult> =>
    (await api.post<LivenessResult>(`${base}/complete`, { session_id: sid })).data

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col items-center px-4 py-5 sm:py-10">
      <div className="w-full max-w-[460px] bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100" style={{ borderTop: `4px solid ${BRAND}` }}>
          <div className="flex items-center gap-2">
            <FoidWordmark height={15} color={BRAND} />
            <span className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wider">Liveness check</span>
          </div>
          {info && !unusable && !result?.passed && (
            <span className="text-[12px] text-neutral-500 flex items-center gap-1">
              <RemixIcon name="ri-time-line" size={13} color="#71717a" /> {mmss(left)}
            </span>
          )}
        </div>

        <div className="p-5 flex flex-col gap-4">
          {fatal && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-link-unlink-m" size={32} color="#a1a1aa" />
              <p className="text-[14px] text-neutral-600">{fatal}</p>
            </div>
          )}

          {!fatal && !info && (
            <div className="flex items-center justify-center gap-2 py-10 text-neutral-400 text-[13px]">
              <RemixIcon name="ri-loader-4-line" size={18} /> Loading…
            </div>
          )}

          {info && unusable && !result && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-time-line" size={32} color="#a1a1aa" />
              <h1 className="text-[16px] font-bold text-neutral-900">
                {info.status === 'completed' ? 'This link has already been used' : 'This link has expired'}
              </h1>
              <p className="text-[13px] text-neutral-500">Start again from FOID on your other device to get a new link.</p>
            </div>
          )}

          {info && !unusable && !result?.passed && (
            <>
              <div>
                <h1 className="text-[17px] font-bold text-neutral-900">Verifying for {info.display_name}</h1>
                <p className="text-[13px] text-neutral-500 mt-1">
                  Not you? Close this page. Hold your phone at eye level in good light, then follow the prompts.
                </p>
              </div>
              <LivenessStage start={start} complete={complete} onFinished={setResult} />
            </>
          )}

          {result?.passed && (
            <div className="flex flex-col items-center text-center gap-2 py-8">
              <RemixIcon name="ri-checkbox-circle-fill" size={42} color={BRAND} />
              <h1 className="text-[17px] font-bold text-neutral-900">You’re verified</h1>
              <p className="text-[13px] text-neutral-500">You can close this page and go back to your other device — it has updated automatically.</p>
            </div>
          )}
        </div>

        <div className="px-5 py-3 bg-neutral-50 border-t border-neutral-100 flex items-center justify-center gap-1.5 text-[11.5px] text-neutral-400">
          <RemixIcon name="ri-lock-2-line" size={13} color="#a1a1aa" /> Secured by <FoidWordmark height={11} color={BRAND} />
        </div>
      </div>
    </div>
  )
}
