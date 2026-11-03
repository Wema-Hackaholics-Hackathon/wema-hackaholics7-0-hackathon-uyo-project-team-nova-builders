/**
 * Turn authenticator-app two-factor on (scan QR → confirm a code) or off (password + code).
 * Works with Google Authenticator, Microsoft Authenticator, Authy, 1Password, …
 */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import QRCode from 'qrcode'
import RemixIcon from '@/components/RemixIcon'
import { api, apiErrorMessage } from '@/lib/api'

const input = 'w-full rounded-xl border border-neutral-200 px-4 py-2.5 text-[13px] outline-none focus:border-[#C800DE] transition-colors'

export default function TwoFactorModal({ mode, onClose, onDone }: {
  mode: 'enable' | 'disable'
  onClose: () => void
  onDone: () => void
}) {
  const [secret, setSecret]     = useState('')
  const [qr, setQr]             = useState('')
  const [code, setCode]         = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy]         = useState(false)
  const [error, setError]       = useState('')

  useEffect(() => {
    if (mode !== 'enable') return
    api.post<{ secret: string; otpauth_uri: string }>('/auth/me/2fa/setup')
      .then(async r => {
        setSecret(r.data.secret)
        setQr(await QRCode.toDataURL(r.data.otpauth_uri, { margin: 1, width: 200 }))
      })
      .catch(e => setError(apiErrorMessage(e, 'Could not start two-factor setup.')))
  }, [mode])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (mode === 'enable') await api.post('/auth/me/2fa/enable', { code })
      else await api.post('/auth/me/2fa/disable', { password, code })
      onDone()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.4)' }}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <div className="font-bold text-[16px] text-neutral-900">
            {mode === 'enable' ? 'Turn on two-factor authentication' : 'Turn off two-factor authentication'}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-full hover:bg-neutral-100 transition-colors">
            <RemixIcon name="ri-close-line" size={18} color="#71717a" />
          </button>
        </div>

        <form onSubmit={e => void submit(e)} className="flex flex-col gap-4">
          {mode === 'enable' ? (
            <>
              <p className="text-[13px] text-neutral-600">
                1. Scan this with an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…).
              </p>
              <div className="self-center w-[200px] h-[200px] rounded-xl border border-neutral-200 flex items-center justify-center">
                {qr ? <img src={qr} alt="Two-factor QR code" width={200} height={200} /> : <RemixIcon name="ri-loader-4-line" size={22} color="#a1a1aa" />}
              </div>
              {secret && (
                <p className="text-[12px] text-neutral-500 text-center">
                  Can't scan? Enter this key: <span className="font-mono select-all text-neutral-800 break-all">{secret}</span>
                </p>
              )}
              <p className="text-[13px] text-neutral-600">2. Enter the 6-digit code the app shows.</p>
            </>
          ) : (
            <div>
              <label className="block text-[13px] font-medium text-neutral-800 mb-1.5">Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required className={input} />
            </div>
          )}
          <div>
            <label className="block text-[13px] font-medium text-neutral-800 mb-1.5">Code from your app</label>
            <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456"
              value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className={`${input} tracking-[0.3em]`} />
          </div>
          {error && <p className="text-[12.5px] text-red-600">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2.5 rounded-full border border-neutral-200 text-[13px] font-bold text-neutral-800 hover:bg-neutral-50 transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={busy || code.length !== 6 || (mode === 'disable' && !password)}
              className="flex-1 py-2.5 rounded-full text-[13px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-60"
              style={{ background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)' }}>
              {busy ? 'Checking…' : mode === 'enable' ? 'Turn on' : 'Turn off'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  )
}
