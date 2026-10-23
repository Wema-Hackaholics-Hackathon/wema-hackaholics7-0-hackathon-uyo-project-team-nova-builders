import { useEffect, useRef, useState } from 'react'
import RemixIcon from './RemixIcon'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'

/* ── Types ──────────────────────────────────────────────────────────── */
interface Message { role: 'ai' | 'user'; text: string }
interface ApiHistory { role: 'user' | 'assistant'; content: string }

/* ── Quick-action chips ─────────────────────────────────────────────── */
const CHIPS = ['Spending this month', 'Estimate my tax', 'Top expense categories']

/* ── Idle nudge messages ────────────────────────────────────────────── */
const NUDGES = [
  "I'm here if you need anything 👋",
  'Ask me about your finances or identity',
  'Want a summary of this month?',
]

/* ── Credit top-up presets ──────────────────────────────────────────── */
const TOPUP_PRESETS = [
  { label: '100 credits',   amount_ngn: 500,   display: '₦500'   },
  { label: '500 credits',   amount_ngn: 2500,  display: '₦2,500' },
  { label: '1,000 credits', amount_ngn: 5000,  display: '₦5,000' },
  { label: '5,000 credits', amount_ngn: 25000, display: '₦25,000' },
]

/* ── Colours ────────────────────────────────────────────────────────── */
const PURPLE = '#9b00d9'
const PURPLE_DARK = '#7B00B0'

/* ── Bot avatar ─────────────────────────────────────────────────────── */
function BotAvatar({ size = 32 }: { size?: number }) {
  return (
    <div className="rounded-full flex items-center justify-center shrink-0"
      style={{ width: size, height: size, background: PURPLE, border: `2px solid ${PURPLE_DARK}` }}>
      <img src="/logo.png" alt="FOID AI" style={{ width: size * 0.55, height: size * 0.55, objectFit: 'contain' }} />
    </div>
  )
}

/* ── Typing indicator ───────────────────────────────────────────────── */
function TypingBubble() {
  return (
    <div className="flex gap-2.5 flex-row">
      <BotAvatar size={32} />
      <div className="rounded-2xl px-4 py-3 flex items-center gap-1"
        style={{ background: '#f0f0f0', borderBottomLeftRadius: 4, minWidth: 56 }}>
        {[0, 1, 2].map(i => (
          <span key={i} className="w-2 h-2 rounded-full"
            style={{ background: '#aaa', display: 'inline-block', animation: `aichat-bounce 1.2s ${i * 0.2}s infinite` }} />
        ))}
      </div>
    </div>
  )
}

/* ── Credit top-up panel (shown inline when credits are 0) ──────────── */
function TopUpPanel({ onClose }: { onClose: () => void }) {
  const [buying, setBuying]         = useState(false)
  const [selectedIdx, setSelected]  = useState(1)          // default: ₦2,500
  const [customAmt, setCustomAmt]   = useState('')
  const [showCustom, setShowCustom] = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const handleBuy = async () => {
    setError(null)
    const preset   = TOPUP_PRESETS[selectedIdx]
    const amount   = showCustom ? parseInt(customAmt, 10) : preset.amount_ngn
    if (!amount || amount < 500) { setError('Minimum purchase is ₦500'); return }

    setBuying(true)
    try {
      const res = await api.post<{ authorization_url: string; credits: number; amount_ngn: number }>(
        '/wallet/initiate-purchase', { amount_ngn: amount }
      )
      // Open Bachs checkout in the same tab — it redirects back to /dashboard/wallet on success
      window.location.href = res.data.authorization_url
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail ?? 'Failed to start checkout. Please try again.')
      setBuying(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 px-5 py-5 border-t border-neutral-100">

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[14px] font-bold text-neutral-900">Top up AI Credits</div>
          <div className="text-[12px] text-neutral-400 mt-0.5">₦5 per credit · no subscription</div>
        </div>
        <button onClick={onClose} className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-neutral-100 transition-colors">
          <RemixIcon name="ri-close-line" size={16} color="#71717a" />
        </button>
      </div>

      {/* Preset grid */}
      <div className="grid grid-cols-2 gap-2">
        {TOPUP_PRESETS.map((p, i) => (
          <button
            key={i}
            onClick={() => { setSelected(i); setShowCustom(false) }}
            className="flex flex-col items-start px-3 py-2.5 rounded-xl border text-left transition-all"
            style={{
              border: !showCustom && selectedIdx === i ? `2px solid ${PURPLE}` : '1.5px solid #e4e4e7',
              background: !showCustom && selectedIdx === i ? '#fdf4ff' : '#fff',
            }}
          >
            <span className="text-[13px] font-bold text-neutral-900">{p.label}</span>
            <span className="text-[11px] text-neutral-400">{p.display}</span>
          </button>
        ))}
      </div>

      {/* Custom amount toggle */}
      <button
        onClick={() => setShowCustom(v => !v)}
        className="text-[12px] font-semibold text-left transition-colors"
        style={{ color: PURPLE }}
      >
        {showCustom ? '← Use preset amount' : 'Enter custom amount →'}
      </button>

      {showCustom && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-full border border-neutral-200 bg-neutral-50">
          <span className="text-[13px] text-neutral-400 shrink-0">₦</span>
          <input
            type="number"
            value={customAmt}
            onChange={e => setCustomAmt(e.target.value)}
            placeholder="e.g. 10000"
            min={500}
            className="flex-1 bg-transparent text-[13px] text-neutral-800 focus:outline-none"
          />
          {customAmt && (
            <span className="text-[11px] text-neutral-400 shrink-0">
              = {Math.floor(parseInt(customAmt, 10) / 5).toLocaleString()} credits
            </span>
          )}
        </div>
      )}

      {error && <p className="text-[12px] text-red-500">{error}</p>}

      {/* Buy button */}
      <button
        onClick={handleBuy}
        disabled={buying}
        className="w-full py-2.5 rounded-full text-[14px] font-bold text-white transition-opacity disabled:opacity-60"
        style={{ background: PURPLE }}
      >
        {buying
          ? 'Opening checkout…'
          : showCustom && customAmt
            ? `Buy ${Math.floor(parseInt(customAmt || '0', 10) / 5).toLocaleString()} credits`
            : `Buy ${TOPUP_PRESETS[selectedIdx].label} for ${TOPUP_PRESETS[selectedIdx].display}`
        }
      </button>
    </div>
  )
}

/* ── FAB button ─────────────────────────────────────────────────────── */
function FabButton({ onClick, nudge }: { onClick: () => void; nudge: string | null }) {
  return (
    <div className="flex flex-col items-end gap-2">
      {nudge && (
        <div className="text-[12px] font-medium px-3 py-1.5 rounded-full shadow-md max-w-[200px] text-center leading-snug"
          style={{ background: '#fff', color: '#18181b', border: '1px solid #e4e4e7' }}>
          {nudge}
        </div>
      )}
      <button onClick={onClick} aria-label="Open AI assistant"
        className="rounded-full flex items-center justify-center shadow-lg transition-transform hover:scale-105 active:scale-95"
        style={{ width: 60, height: 60, background: PURPLE, border: `3px solid rgba(155,0,217,0.35)`, outline: `4px solid rgba(155,0,217,0.18)` }}>
        <img src="/logo-white.png" alt="" style={{ width: 30, height: 30, objectFit: 'contain' }} />
      </button>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════
   Main component
═══════════════════════════════════════════════════════════════════════ */
export default function AiChat() {
  const { user } = useAuth()
  const firstName = user?.firstName || (user as unknown as Record<string, string>)?.first_name || 'there'

  const [open, setOpen]               = useState(false)
  const [input, setInput]             = useState('')
  const [nudge, setNudge]             = useState<string | null>(null)
  const [nudgeIdx, setNudgeIdx]       = useState(0)
  const [typing, setTyping]           = useState(false)
  const [credits, setCredits]         = useState<number | null>(null)
  const [showTopUp, setShowTopUp]     = useState(false)
  const [messages, setMessages]       = useState<Message[]>([{
    role: 'ai',
    text: `Hi ${firstName} 👋 — I'm your FOID AI assistant. Ask me about your spending, income, tax estimate, or credential status.`,
  }])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)

  // ── Fetch wallet balance when chat opens ─────────────────────────────
  useEffect(() => {
    if (!open) return
    api.get<{ balance: number }>('/wallet')
      .then(r => setCredits(r.data.balance))
      .catch(() => {/* unverified users will get 403 — just leave null */})
  }, [open])

  // ── Update greeting when auth resolves ──────────────────────────────
  useEffect(() => {
    setMessages([{
      role: 'ai',
      text: `Hi ${firstName} 👋 — I'm your FOID AI assistant. Ask me about your spending, income, tax estimate, or credential status.`,
    }])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstName])

  // ── Nudge interval ───────────────────────────────────────────────────
  useEffect(() => {
    if (open) { setNudge(null); return }
    const id = setInterval(() => {
      setNudge(NUDGES[nudgeIdx % NUDGES.length])
      setNudgeIdx(i => i + 1)
      setTimeout(() => setNudge(null), 4000)
    }, 20_000)
    const first = setTimeout(() => { setNudge(NUDGES[0]); setTimeout(() => setNudge(null), 4000) }, 5000)
    return () => { clearInterval(id); clearTimeout(first) }
  }, [open, nudgeIdx])

  // ── Scroll to bottom ─────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, open, typing, showTopUp])

  // ── Focus input ──────────────────────────────────────────────────────
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 120) }, [open])

  function buildHistory(current: Message[]): ApiHistory[] {
    return current.map(m => ({
      role: m.role === 'ai' ? 'assistant' : 'user',
      content: m.text,
    })) as ApiHistory[]
  }

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || typing) return

    setMessages(prev => [...prev, { role: 'user', text: trimmed }])
    setInput('')
    setTyping(true)
    setShowTopUp(false)

    try {
      const res = await api.post<{ reply: string; credits_remaining: number }>('/ledger/chat', {
        message: trimmed,
        history: buildHistory(messages),
      })
      setCredits(res.data.credits_remaining)
      setMessages(prev => [...prev, { role: 'ai', text: res.data.reply }])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 402) {
        setCredits(0)
        setShowTopUp(true)
        setMessages(prev => [...prev, {
          role: 'ai',
          text: "⚠️ You've used all your AI credits. Top up below to keep chatting — it's just ₦5 per message.",
        }])
      } else {
        setMessages(prev => [...prev, {
          role: 'ai',
          text: axiosErr.response?.data?.detail
            ? `Error: ${axiosErr.response.data.detail}`
            : 'Sorry, something went wrong. Please try again.',
        }])
      }
    } finally {
      setTyping(false)
    }
  }

  // ── Credit colour ────────────────────────────────────────────────────
  const creditColour = credits === null ? '#86efac' :
    credits === 0 ? '#fca5a5' :
    credits < 10  ? '#fde68a' : '#86efac'

  const creditLabel = credits === null ? 'Loading…' :
    credits === 0 ? '0 credits · Top up' :
    `${credits} credit${credits === 1 ? '' : 's'}`

  return (
    <div className="fixed bottom-4 right-4 md:bottom-6 md:right-6 z-50 flex flex-col items-end gap-3">

      <style>{`
        @keyframes aichat-bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
      `}</style>

      {/* ── Chat panel ── */}
      {open && (
        <div className="flex flex-col rounded-2xl md:rounded-3xl overflow-hidden shadow-2xl"
          style={{ width: 'min(390px, calc(100vw - 32px))', maxHeight: '88vh', background: '#fff', border: '1px solid #e4e4e7' }}>

          {/* ── Header ── */}
          <div className="flex items-start justify-between px-5 py-4" style={{ background: PURPLE }}>
            <div className="flex items-center gap-3">
              <img src="/logo-white.png" alt="FOID" style={{ width: 28, height: 28, objectFit: 'contain' }} />
              <div>
                <div className="text-white font-extrabold text-[17px] leading-tight"
                  style={{ fontFamily: "'Neue Machina', sans-serif" }}>
                  Foid AI
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: creditColour }} />
                  <span className="text-[12px] font-semibold" style={{ color: creditColour }}>
                    {creditLabel}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Top-up shortcut button */}
              <button
                onClick={() => setShowTopUp(v => !v)}
                title="Buy credits"
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors"
                style={{ background: 'rgba(255,255,255,0.18)', color: '#fff' }}
              >
                <RemixIcon name="ri-add-circle-line" size={14} color="#fff" />
                Top up
              </button>
              <button onClick={() => setOpen(false)} aria-label="Close"
                className="w-8 h-8 rounded-full flex items-center justify-center transition-colors"
                style={{ background: 'rgba(255,255,255,0.18)' }}>
                <RemixIcon name="ri-close-line" size={18} color="#fff" clickable />
              </button>
            </div>
          </div>

          {/* ── Messages ── */}
          <div className="flex-1 overflow-y-auto px-4 py-5 flex flex-col gap-4"
            style={{ minHeight: 220, maxHeight: 340 }}>
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-2.5 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                {m.role === 'ai' && <BotAvatar size={32} />}
                <div
                  className="rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed max-w-[82%] whitespace-pre-wrap"
                  style={m.role === 'ai'
                    ? { background: '#f0f0f0', color: '#3a3a3a', borderBottomLeftRadius: 4 }
                    : { background: PURPLE, color: '#fff', borderBottomRightRadius: 4 }
                  }
                >
                  {m.text}
                </div>
              </div>
            ))}
            {typing && <TypingBubble />}
            <div ref={bottomRef} />
          </div>

          {/* ── Top-up panel (inline) ── */}
          {showTopUp && <TopUpPanel onClose={() => setShowTopUp(false)} />}

          {/* ── Quick chips (hidden when top-up open) ── */}
          {!showTopUp && (
            <div className="flex gap-2 px-4 pb-3 flex-wrap border-t border-neutral-100 pt-3">
              {CHIPS.map(chip => (
                <button key={chip} onClick={() => send(chip)} disabled={typing || credits === 0}
                  className="text-[12px] font-semibold px-3 py-1.5 rounded-full border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors whitespace-nowrap disabled:opacity-40">
                  {chip}
                </button>
              ))}
            </div>
          )}

          {/* ── Input row ── */}
          {!showTopUp && (
            <div className="px-4 pb-4">
              {credits === 0 && (
                <p className="text-center text-[12px] text-neutral-400 mb-2">
                  No credits remaining —{' '}
                  <button onClick={() => setShowTopUp(true)} className="font-semibold underline" style={{ color: PURPLE }}>
                    top up to continue
                  </button>
                </p>
              )}
              <div className="flex items-center gap-2 px-4 py-2.5 rounded-full"
                style={{ background: credits === 0 ? '#fdf4ff' : '#f4f4f5', border: `1px solid ${credits === 0 ? '#e879f9' : '#e4e4e7'}` }}>
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && send(input)}
                  disabled={typing || credits === 0}
                  placeholder={credits === 0 ? 'Top up credits to continue…' : 'Ask about your finances, identity or credit score'}
                  className="flex-1 bg-transparent text-[13px] text-neutral-800 placeholder:text-neutral-400 focus:outline-none disabled:opacity-50"
                />
                <button onClick={() => send(input)} disabled={typing || !input.trim() || credits === 0}
                  aria-label="Send" className="shrink-0 transition-opacity disabled:opacity-30"
                  style={{ opacity: input.trim() && !typing && credits !== 0 ? 1 : 0.35 }}>
                  <RemixIcon name="ri-send-plane-fill" size={20} color={PURPLE} clickable />
                </button>
              </div>
            </div>
          )}

        </div>
      )}

      {/* ── FAB ── */}
      <FabButton onClick={() => setOpen(o => !o)} nudge={open ? null : nudge} />
    </div>
  )
}
