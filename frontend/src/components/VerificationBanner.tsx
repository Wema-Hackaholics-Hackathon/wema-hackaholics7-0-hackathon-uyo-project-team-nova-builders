/**
 * VerificationBanner — sticky brand-colour bar shown when email is unverified.
 *
 * Desktop: marquee-free text + "Verify" button on the right
 * Mobile:  marquee scrolling text + fixed "Verify" button on the right
 *
 * Clicking "Verify" opens VerifyEmailModal — an inline OTP form with a
 * resend-code countdown timer.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'

/* ── Banner ──────────────────────────────────────────────────────────────── */

export default function VerificationBanner() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)

  if (!user || user.email_verified) return null

  return (
    <>
      <div
        role="alert"
        style={{
          background: 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)',
          color: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '0 16px',
          height: 40,
          minHeight: 40,
          flexShrink: 0,
          position: 'relative',
          overflow: 'hidden',
          zIndex: 40,
        }}
      >
        {/* Desktop text — static */}
        <span
          className="hidden md:block"
          style={{
            fontSize: 13,
            fontWeight: 500,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            flex: 1,
          }}
        >
          ⚠ Your email is not verified — you are in view-only mode.
          Verify now to unlock all features. Unverified accounts are automatically
          deleted after 3 days.
        </span>

        {/* Mobile text — marquee */}
        <div
          className="block md:hidden"
          style={{ flex: 1, overflow: 'hidden', position: 'relative', height: '100%' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
            <MarqueeText>
              ⚠ Your email is not verified — you are in view-only mode. Verify now to
              unlock all features. Unverified accounts are deleted after 3 days.
              &nbsp;&nbsp;&nbsp;&nbsp;⚠ Your email is not verified — you are in
              view-only mode. Verify now to unlock all features. Unverified accounts
              are deleted after 3 days.
            </MarqueeText>
          </div>
        </div>

        {/* Verify button — always visible on the right */}
        <button
          type="button"
          onClick={() => setOpen(true)}
          style={{
            flexShrink: 0,
            background: '#fff',
            color: '#C800DE',
            border: 'none',
            borderRadius: 6,
            padding: '4px 14px',
            fontSize: 12,
            fontWeight: 700,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            lineHeight: '20px',
          }}
        >
          Verify
        </button>
      </div>

      {open && <VerifyEmailModal onClose={() => setOpen(false)} />}
    </>
  )
}

/* ── CSS marquee ─────────────────────────────────────────────────────────── */

function MarqueeText({ children }: { children: React.ReactNode }) {
  return (
    <>
      <style>{`
        @keyframes foid-marquee {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .foid-marquee-inner {
          display: inline-flex;
          white-space: nowrap;
          animation: foid-marquee 22s linear infinite;
          font-size: 12px;
          font-weight: 500;
        }
      `}</style>
      <span className="foid-marquee-inner">{children}</span>
    </>
  )
}

/* ── Modal ───────────────────────────────────────────────────────────────── */

const RESEND_COOLDOWN = 60  // seconds

function VerifyEmailModal({ onClose }: { onClose: () => void }) {
  const { user, verifyEmail, resendVerification } = useAuth()

  const [code, setCode]             = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]           = useState('')
  const [success, setSuccess]       = useState(false)

  const [cooldown, setCooldown]       = useState(0)
  const [resendMsg, setResendMsg]     = useState('')
  const cooldownRef                   = useRef<ReturnType<typeof setInterval> | null>(null)

  const startCooldown = useCallback(() => {
    setCooldown(RESEND_COOLDOWN)
    cooldownRef.current = setInterval(() => {
      setCooldown(prev => {
        if (prev <= 1) {
          clearInterval(cooldownRef.current!)
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }, [])

  // Clean up interval on unmount
  useEffect(() => () => { if (cooldownRef.current) clearInterval(cooldownRef.current) }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!user || code.length !== 6) return
    setSubmitting(true)
    setError('')

    const result = await verifyEmail(user.email, code)
    setSubmitting(false)

    if (result.ok) {
      setSuccess(true)
      // Close after a short success flash
      setTimeout(onClose, 1800)
    } else {
      setError(result.error ?? 'Invalid or expired code. Please try again.')
    }
  }

  const handleResend = async () => {
    if (!user || cooldown > 0) return
    setResendMsg('')
    setError('')

    const result = await resendVerification(user.email)
    if (result.ok) {
      setResendMsg('A new code has been sent to your email.')
      startCooldown()
    } else {
      setError(result.error ?? 'Could not resend code.')
    }
  }

  return (
    /* Backdrop */
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.45)',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Panel */}
      <div
        style={{
          background: '#fff',
          borderRadius: 16,
          padding: '32px 28px 28px',
          width: '100%',
          maxWidth: 420,
          margin: '0 16px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.22)',
          position: 'relative',
        }}
      >
        {/* Close */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute', top: 16, right: 16,
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#9ca3af', lineHeight: 1,
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M2 2l14 14M16 2L2 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>

        {/* Icon */}
        <div style={{
          width: 48, height: 48, borderRadius: 12,
          background: 'linear-gradient(135deg, #f3e6ff 0%, #fce7ff 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 16,
        }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M3 8l7.89 5.26a2 2 0 0 0 2.22 0L21 8M5 19h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2z"
              stroke="#C800DE" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>

        {success ? (
          <div style={{ textAlign: 'center', padding: '8px 0' }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: 'linear-gradient(135deg, #C800DE, #9000A8)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M5 12l5 5L19 7" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p style={{ fontSize: 17, fontWeight: 700, color: '#111', marginBottom: 6 }}>Email verified!</p>
            <p style={{ fontSize: 13, color: '#6b7280' }}>Your account is now fully active.</p>
          </div>
        ) : (
          <>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#111', marginBottom: 6 }}>
              Verify your email
            </h2>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 24, lineHeight: 1.6 }}>
              Enter the 6-digit code sent to{' '}
              <strong style={{ color: '#111' }}>{user?.email}</strong>
            </p>

            <form onSubmit={handleSubmit}>
              {/* OTP input */}
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={e => {
                  const v = e.target.value.replace(/\D/g, '').slice(0, 6)
                  setCode(v)
                  setError('')
                }}
                style={{
                  width: '100%',
                  border: error ? '1.5px solid #ef4444' : '1.5px solid #e5e7eb',
                  borderRadius: 10,
                  padding: '12px 14px',
                  fontSize: 22,
                  letterSpacing: 8,
                  textAlign: 'center',
                  outline: 'none',
                  marginBottom: 8,
                  fontWeight: 700,
                  color: '#111',
                  boxSizing: 'border-box',
                }}
              />

              {error && (
                <p style={{ fontSize: 12, color: '#ef4444', marginBottom: 12 }}>{error}</p>
              )}
              {resendMsg && !error && (
                <p style={{ fontSize: 12, color: '#16a34a', marginBottom: 12 }}>{resendMsg}</p>
              )}

              <button
                type="submit"
                disabled={submitting || code.length < 6}
                style={{
                  width: '100%',
                  padding: '12px 0',
                  borderRadius: 10,
                  border: 'none',
                  background: code.length === 6 && !submitting
                    ? 'linear-gradient(90deg, #C800DE 0%, #9000A8 100%)'
                    : '#e5e7eb',
                  color: code.length === 6 && !submitting ? '#fff' : '#9ca3af',
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: code.length === 6 && !submitting ? 'pointer' : 'not-allowed',
                  marginBottom: 16,
                  transition: 'background 0.15s',
                }}
              >
                {submitting ? 'Verifying…' : 'Verify Email'}
              </button>
            </form>

            <div style={{ textAlign: 'center' }}>
              <span style={{ fontSize: 12, color: '#6b7280' }}>Didn't receive a code? </span>
              <button
                type="button"
                onClick={handleResend}
                disabled={cooldown > 0}
                style={{
                  background: 'none', border: 'none',
                  fontSize: 12, fontWeight: 600,
                  color: cooldown > 0 ? '#9ca3af' : '#C800DE',
                  cursor: cooldown > 0 ? 'default' : 'pointer',
                  padding: 0,
                }}
              >
                {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
