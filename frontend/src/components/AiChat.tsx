import { useEffect, useRef, useState } from 'react'
import RemixIcon from './RemixIcon'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'

/* ── Types ──────────────────────────────────────────────────────────── */
interface Message {
  role: 'ai' | 'user'
  text: string
}

// Maps onto ChatMessage in the backend schema
interface ApiHistory {
  role: 'user' | 'assistant'
  content: string
}

/* ── Quick-action chips ─────────────────────────────────────────────── */
const CHIPS = ['Spending this month', 'Estimate my tax', 'Top expense categories']

/* ── Idle nudge messages (cycle at intervals) ───────────────────────── */
const NUDGES = [
  "I'm here if you need anything 👋",
  'Ask me about your finances or identity',
  'Want a summary of this month?',
]

/* ── Colours ────────────────────────────────────────────────────────── */
const PURPLE = '#9b00d9'
const PURPLE_DARK = '#7B00B0'

/* ── Small avatar used in chat bubbles ──────────────────────────────── */
function BotAvatar({ size = 32 }: { size?: number }) {
  return (
    <div
      className="rounded-full flex items-center justify-center shrink-0"
      style={{
        width: size, height: size,
        background: PURPLE,
        border: `2px solid ${PURPLE_DARK}`,
      }}
    >
      <img src="/logo.png" alt="FOID AI" style={{ width: size * 0.55, height: size * 0.55, objectFit: 'contain' }} />
    </div>
  )
}

/* ── Animated typing indicator ──────────────────────────────────────── */
function TypingBubble() {
  return (
    <div className="flex gap-2.5 flex-row">
      <BotAvatar size={32} />
      <div
        className="rounded-2xl px-4 py-3 flex items-center gap-1"
        style={{ background: '#f0f0f0', borderBottomLeftRadius: 4, minWidth: 56 }}
      >
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="w-2 h-2 rounded-full"
            style={{
              background: '#aaa',
              display: 'inline-block',
              animation: `bounce 1.2s ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

/* ── FAB button ─────────────────────────────────────────────────────── */
function FabButton({ onClick, nudge }: { onClick: () => void; nudge: string | null }) {
  return (
    <div className="flex flex-col items-end gap-2">
      {/* nudge pill */}
      {nudge && (
        <div
          className="text-[12px] font-medium px-3 py-1.5 rounded-full shadow-md max-w-[200px] text-center leading-snug"
          style={{ background: '#fff', color: '#18181b', border: '1px solid #e4e4e7' }}
        >
          {nudge}
        </div>
      )}

      {/* FAB */}
      <button
        onClick={onClick}
        aria-label="Open AI assistant"
        className="rounded-full flex items-center justify-center shadow-lg transition-transform hover:scale-105 active:scale-95"
        style={{
          width: 60, height: 60,
          background: PURPLE,
          border: `3px solid rgba(155,0,217,0.35)`,
          outline: `4px solid rgba(155,0,217,0.18)`,
        }}
      >
        <img src="/logo-white.png" alt="" style={{ width: 30, height: 30, objectFit: 'contain' }} />
      </button>
    </div>
  )
}

/* ── Main component ─────────────────────────────────────────────────── */
export default function AiChat() {
  const { user } = useAuth()
  const firstName = user?.firstName || user?.first_name || 'there'

  const [open, setOpen]         = useState(false)
  const [input, setInput]       = useState('')
  const [nudge, setNudge]       = useState<string | null>(null)
  const [nudgeIdx, setNudgeIdx] = useState(0)
  const [typing, setTyping]     = useState(false)
  const [creditsLeft, setCreditsLeft] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'ai',
      text: `Hi ${firstName} 👋 — I'm your FOID AI assistant. Ask me about your spending, income, tax estimate, or credential status.`,
    },
  ])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)

  // Update greeting when user loads (it may be null on first render)
  useEffect(() => {
    setMessages([{
      role: 'ai',
      text: `Hi ${firstName} 👋 — I'm your FOID AI assistant. Ask me about your spending, income, tax estimate, or credential status.`,
    }])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstName])

  /* Nudge interval — show a message every 20 s while closed */
  useEffect(() => {
    if (open) { setNudge(null); return }
    const id = setInterval(() => {
      setNudge(NUDGES[nudgeIdx % NUDGES.length])
      setNudgeIdx(i => i + 1)
      setTimeout(() => setNudge(null), 4000)
    }, 20_000)
    const first = setTimeout(() => {
      setNudge(NUDGES[0])
      setTimeout(() => setNudge(null), 4000)
    }, 5000)
    return () => { clearInterval(id); clearTimeout(first) }
  }, [open, nudgeIdx])

  /* Scroll to bottom whenever messages or typing indicator changes */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open, typing])

  /* Focus input when opened */
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 120)
  }, [open])

  /* Build history array for the backend (last 20 messages, alternating roles) */
  function buildHistory(current: Message[]): ApiHistory[] {
    return current
      .filter(m => m.role === 'user' || m.role === 'ai')
      .map(m => ({
        role: m.role === 'ai' ? 'assistant' : 'user',
        content: m.text,
      })) as ApiHistory[]
  }

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || typing) return

    const userMsg: Message = { role: 'user', text: trimmed }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setTyping(true)

    try {
      const res = await api.post<{ reply: string; credits_remaining: number }>('/ledger/chat', {
        message: trimmed,
        history: buildHistory(messages), // history before this new message
      })
      setCreditsLeft(res.data.credits_remaining)
      setMessages(prev => [...prev, { role: 'ai', text: res.data.reply }])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      let errText = 'Sorry, something went wrong. Please try again.'
      if (axiosErr.response?.status === 402) {
        errText = '⚠️ You\'ve run out of AI credits. Top up in the AI Credit Wallet to continue.'
      } else if (axiosErr.response?.data?.detail) {
        errText = `Error: ${axiosErr.response.data.detail}`
      }
      setMessages(prev => [...prev, { role: 'ai', text: errText }])
    } finally {
      setTyping(false)
    }
  }

  return (
    /* Fixed container — bottom-right corner, above everything */
    <div className="fixed bottom-4 right-4 md:bottom-6 md:right-6 z-50 flex flex-col items-end gap-3">

      {/* bounce keyframes */}
      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
      `}</style>

      {/* ── Chat panel ── */}
      {open && (
        <div
          className="flex flex-col rounded-2xl md:rounded-3xl overflow-hidden shadow-2xl"
          style={{
            width: 'min(380px, calc(100vw - 32px))',
            maxHeight: '82vh',
            background: '#fff',
            border: '1px solid #e4e4e7',
          }}
        >
          {/* Header */}
          <div
            className="flex items-start justify-between px-5 py-4"
            style={{ background: PURPLE }}
          >
            <div className="flex items-center gap-3">
              <img src="/logo-white.png" alt="FOID" style={{ width: 28, height: 28, objectFit: 'contain' }} />
              <div>
                <div className="text-white font-extrabold text-[17px] leading-tight"
                  style={{ fontFamily: "'Neue Machina', sans-serif" }}>
                  Foid AI
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="w-2 h-2 rounded-full bg-green-400 shrink-0" />
                  <span className="text-[12px] font-semibold text-green-300">
                    Online{creditsLeft !== null ? ` · ${creditsLeft} credits` : ' · AI credits active'}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="w-8 h-8 rounded-full flex items-center justify-center transition-colors"
              style={{ background: 'rgba(255,255,255,0.18)' }}
            >
              <RemixIcon name="ri-close-line" size={18} color="#fff" clickable />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-5 flex flex-col gap-4" style={{ minHeight: 260, maxHeight: 360 }}>
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-2.5 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                {m.role === 'ai' && <BotAvatar size={32} />}
                <div
                  className="rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed max-w-[80%] whitespace-pre-wrap"
                  style={
                    m.role === 'ai'
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

          {/* Quick chips */}
          <div className="flex gap-2 px-4 pb-3 flex-wrap border-t border-neutral-100 pt-3">
            {CHIPS.map(chip => (
              <button
                key={chip}
                onClick={() => send(chip)}
                disabled={typing}
                className="text-[12px] font-semibold px-3 py-1.5 rounded-full border border-neutral-200 text-neutral-700 hover:bg-neutral-50 transition-colors whitespace-nowrap disabled:opacity-40"
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Input row */}
          <div className="px-4 pb-4">
            <div
              className="flex items-center gap-2 px-4 py-2.5 rounded-full"
              style={{ background: '#f4f4f5', border: '1px solid #e4e4e7' }}
            >
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send(input)}
                disabled={typing}
                placeholder="Ask about your finances, identity or credit score"
                className="flex-1 bg-transparent text-[13px] text-neutral-800 placeholder:text-neutral-400 focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={() => send(input)}
                disabled={typing || !input.trim()}
                aria-label="Send"
                className="shrink-0 transition-opacity disabled:opacity-30"
                style={{ opacity: input.trim() && !typing ? 1 : 0.35 }}
              >
                <RemixIcon name="ri-send-plane-fill" size={20} color={PURPLE} clickable />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── FAB ── */}
      <FabButton onClick={() => setOpen(o => !o)} nudge={open ? null : nudge} />
    </div>
  )
}
