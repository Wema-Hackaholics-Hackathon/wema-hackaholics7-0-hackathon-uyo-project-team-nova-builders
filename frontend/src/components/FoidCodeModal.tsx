/**
 * "View my FOID code" — a QR code someone can scan (a bank teller, a landlord, a
 * merchant) to see that your FOID credential is real and what you've verified,
 * without you reading out your NIN or BVN. The code lasts 10 minutes and is
 * renewed with one click. See backend routers/credentials.py (FOID code).
 */
import { useCallback, useEffect, useState } from 'react'
import QRCode from 'qrcode'
import FoidWordmark from '@/components/FoidWordmark'
import RemixIcon from '@/components/RemixIcon'
import { api, apiErrorMessage } from '@/lib/api'

const BRAND = '#C800DE'

interface Code { token: string; url: string; code: string; expires_at: string; ttl_seconds: number }

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function FoidCodeModal({ onClose }: { onClose: () => void }) {
  const [code, setCode]     = useState<Code | null>(null)
  const [qr, setQr]         = useState('')
  const [error, setError]   = useState('')
  const [left, setLeft]     = useState(0)
  const [copied, setCopied] = useState(false)

  const issue = useCallback(async () => {
    setError('')
    setCopied(false)
    try {
      const c = (await api.post<Code>('/credentials/me/code')).data
      setCode(c)
      setLeft(c.ttl_seconds)
      setQr(await QRCode.toDataURL(c.url, { margin: 1, width: 240, color: { dark: '#18181b', light: '#ffffff' } }))
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not create your FOID code.'))
    }
  }, [])

  useEffect(() => { void issue() }, [issue])
  useEffect(() => {
    const t = setInterval(() => setLeft(l => Math.max(0, l - 1)), 1000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const expired = !!code && left <= 0

  async function copy() {
    if (!code) return
    await navigator.clipboard.writeText(code.url)
    setCopied(true)
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-[400px] bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <div className="flex items-center gap-2">
            <FoidWordmark height={15} color={BRAND} />
            <span className="text-[12px] font-semibold text-neutral-400 uppercase tracking-wider">My FOID code</span>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-neutral-100">
            <RemixIcon name="ri-close-line" size={20} color="#71717a" clickable />
          </button>
        </div>

        <div className="p-5 flex flex-col items-center gap-4 text-center">
          <p className="text-[13px] text-neutral-500">
            Let someone scan this to confirm your FOID credential. They see your first name, last initial and
            what you've verified — never your NIN, BVN, date of birth or contact details.
          </p>

          <div className="relative w-[240px] h-[240px] rounded-xl border border-neutral-200 flex items-center justify-center bg-white">
            {qr && <img src={qr} alt="Your FOID code" width={240} height={240} className={expired ? 'opacity-10' : ''} />}
            {!qr && !error && <RemixIcon name="ri-loader-4-line" size={24} color="#a1a1aa" />}
            {error && <p className="text-[12.5px] text-red-500 px-4">{error}</p>}
            {expired && (
              <button onClick={() => void issue()}
                className="absolute inset-0 m-auto w-max h-max px-4 py-2 rounded-full bg-brand-500 text-white text-[13px] font-semibold hover:bg-brand-600">
                Get a new code
              </button>
            )}
          </div>

          {code && (
            <>
              <div className="text-[15px] font-bold tracking-wider text-neutral-900">{code.code}</div>
              <div className="text-[12px] text-neutral-500 flex items-center gap-1">
                <RemixIcon name="ri-time-line" size={13} color="#71717a" />
                {expired ? 'Expired' : `Expires in ${mmss(left)}`}
              </div>
            </>
          )}

          <div className="flex gap-2 w-full">
            <button onClick={() => void copy()} disabled={!code || expired}
              className="flex-1 py-2.5 border border-neutral-200 rounded-xl text-[13px] font-semibold text-neutral-800 hover:bg-neutral-50 disabled:opacity-50 flex items-center justify-center gap-1.5">
              <RemixIcon name={copied ? 'ri-check-line' : 'ri-link'} size={16} /> {copied ? 'Link copied' : 'Copy link'}
            </button>
            <button onClick={() => void issue()}
              className="flex-1 py-2.5 border border-neutral-200 rounded-xl text-[13px] font-semibold text-neutral-800 hover:bg-neutral-50 flex items-center justify-center gap-1.5">
              <RemixIcon name="ri-refresh-line" size={16} /> New code
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
