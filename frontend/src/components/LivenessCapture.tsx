/**
 * Server-verified liveness check (faceliveness SDK on the backend).
 *
 * Camera → 320×240 JPEG frames → POST {endpoint}/{id}/frame, one at a time.
 * Used by the FOID dashboard (endpoint "/auth/me/liveness") and by the hosted
 * business verification page (endpoint "/hosted/sessions/{token}/liveness"). The server runs the engine, decides pass/fail and signs the receipt;
 * this component only shows the prompts. Frames are sent un-mirrored — only
 * the preview is flipped with CSS.
 */
import { useEffect, useRef, useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import { api } from '@/lib/api'
import type { LivenessFrameState, LivenessPurpose, LivenessStart } from '@/types/foid'

/** Fields every complete endpoint returns (first-party adds enrolment/match details). */
export interface LivenessOutcome {
  passed: boolean
  message: string
}

const FRAME_WIDTH = 320
const FRAME_HEIGHT = 240
const MIN_FRAME_INTERVAL_MS = 100

const PROMPTS: Record<string, string> = {
  blink: 'Blink',
  turn_left: 'Turn your head to your left',
  turn_right: 'Turn your head to your right',
  open_mouth: 'Open your mouth wide',
}

const FAILURES: Record<string, string> = {
  timeout: 'The check took too long.',
  step_timeout: "That step wasn't completed in time.",
  face_lost: 'Your face left the camera view.',
  multiple_faces: 'More than one face was in view.',
  spoof_suspected: 'The image looked like a photo or screen.',
}

type Phase = 'consent' | 'starting' | 'running' | 'finishing' | 'result'

function errorDetail(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

export default function LivenessCapture<T extends LivenessOutcome = LivenessOutcome>({
  purpose = 'enrol',
  endpoint = '/auth/me/liveness',
  consentRequired = purpose === 'enrol',
  autoStart = purpose === 'verify',
  onComplete,
  onAttempt,
}: {
  purpose?: LivenessPurpose
  /** Base path of the start / frame / complete routes */
  endpoint?: string
  /** Show the biometric consent checkbox before starting */
  consentRequired?: boolean
  /** Open the camera immediately instead of showing a start button */
  autoStart?: boolean
  /** Called when a check passes */
  onComplete: (result: T) => void
  /** Called after every finished attempt, passed or not */
  onAttempt?: (result: T) => void
}) {
  const videoRef  = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const activeRef = useRef(false)

  const [phase, setPhase]       = useState<Phase>(autoStart ? 'starting' : 'consent')
  const [consent, setConsent]   = useState(false)
  const [prompt, setPrompt]     = useState('Position your face in the frame')
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [error, setError]       = useState('')
  const [result, setResult]     = useState<T | null>(null)

  function stopCamera() {
    activeRef.current = false
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
  }

  useEffect(() => stopCamera, [])
  useEffect(() => {
    if (autoStart) void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function run() {
    setError('')
    setResult(null)
    setPhase('starting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      })
      streamRef.current = stream
      const video = videoRef.current
      if (!video) throw new Error('no video element')
      video.srcObject = stream
      await video.play()
    } catch {
      stopCamera()
      setError('Camera access is needed for the liveness check. Allow it in your browser and try again.')
      setPhase(autoStart ? 'result' : 'consent')
      return
    }

    let session: LivenessStart
    try {
      session = (await api.post<LivenessStart>(`${endpoint}/start`, { purpose, consent })).data
    } catch (e) {
      stopCamera()
      setError(errorDetail(e, 'Could not start the liveness check.'))
      setPhase(autoStart ? 'result' : 'consent')
      return
    }

    const total = session.challenges.length
    setProgress({ done: 0, total })
    setPrompt(PROMPTS[session.challenges[0]] ?? 'Look at the camera')
    setPhase('running')
    activeRef.current = true

    const canvas = document.createElement('canvas')
    canvas.width = FRAME_WIDTH
    canvas.height = FRAME_HEIGHT
    const ctx = canvas.getContext('2d')
    let state: LivenessFrameState | null = null

    while (activeRef.current) {
      const started = performance.now()
      const video = videoRef.current
      if (!ctx || !video) break
      ctx.drawImage(video, 0, 0, FRAME_WIDTH, FRAME_HEIGHT)
      const blob = await new Promise<Blob | null>(r => canvas.toBlob(r, 'image/jpeg', 0.8))
      if (!blob) continue
      try {
        state = (await api.post<LivenessFrameState>(
          `${endpoint}/${session.session_id}/frame`,
          blob,
          { headers: { 'Content-Type': 'image/jpeg' } },
        )).data
      } catch (e) {
        const code = (e as { response?: { status?: number } })?.response?.status
        if (code === 429) continue
        stopCamera()
        setError(errorDetail(e, 'Connection lost during the liveness check.'))
        setPhase('result')
        return
      }
      if (state.done) break
      if (state.face_count === 0) setPrompt('Position your face in the frame')
      else if (state.face_count > 1) setPrompt('Only one face should be in view')
      else setPrompt(PROMPTS[state.current_challenge ?? ''] ?? 'Look at the camera')
      setProgress({ done: total - state.remaining, total })
      const wait = MIN_FRAME_INTERVAL_MS - (performance.now() - started)
      if (wait > 0) await sleep(wait)
    }

    const cancelled = !activeRef.current && !state?.done
    stopCamera()
    if (cancelled) return

    setPhase('finishing')
    try {
      const res = (await api.post<T>(`${endpoint}/${session.session_id}/complete`)).data
      setResult(res)
      setPhase('result')
      onAttempt?.(res)
      if (!res.passed) {
        setError(FAILURES[state?.fail_reason ?? ''] ?? res.message)
      } else {
        onComplete(res)
      }
    } catch (e) {
      setError(errorDetail(e, 'Could not complete the liveness check.'))
      setPhase('result')
    }
  }

  const showCamera = phase === 'starting' || phase === 'running'

  return (
    <div className="mt-3 p-4 rounded-xl bg-neutral-50 border border-neutral-200 flex flex-col gap-3">
      {/* Camera preview — mirrored for the user only */}
      <div
        className={[
          'relative w-full max-w-[360px] mx-auto aspect-[4/3] rounded-xl overflow-hidden bg-neutral-900',
          showCamera ? '' : 'hidden',
        ].join(' ')}
      >
        <video
          ref={videoRef}
          playsInline
          muted
          className="w-full h-full object-cover"
          style={{ transform: 'scaleX(-1)' }}
        />
        <div className="absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/70 to-transparent">
          <div className="text-[14px] font-semibold text-white text-center">
            {phase === 'starting' ? 'Starting camera…' : prompt}
          </div>
          {progress.total > 0 && (
            <div className="flex justify-center gap-1.5 mt-2">
              {Array.from({ length: progress.total }, (_, i) => (
                <span
                  key={i}
                  className={['w-2 h-2 rounded-full', i < progress.done ? 'bg-brand-400' : 'bg-white/40'].join(' ')}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {phase === 'consent' && (
        <>
          <div className="flex items-center gap-2 text-[13px] text-neutral-600">
            <RemixIcon name="ri-camera-line" size={16} color="#a1a1aa" />
            <span>Allow camera access, then follow the on-screen prompts</span>
          </div>
          {consentRequired && <label className="flex items-start gap-2 text-[12.5px] text-neutral-600 cursor-pointer">
            <input
              type="checkbox"
              checked={consent}
              onChange={e => setConsent(e.target.checked)}
              className="mt-0.5 accent-brand-500"
            />
            <span>
              I consent to FOID processing my face to verify my identity. An encrypted face
              template is stored and I can delete it at any time from Profile Settings.
            </span>
          </label>}
        </>
      )}

      {phase === 'finishing' && (
        <div className="flex items-center gap-2 text-[13px] text-neutral-600">
          <RemixIcon name="ri-loader-4-line" size={16} color="#a1a1aa" />
          <span>Verifying your face…</span>
        </div>
      )}

      {phase === 'result' && result?.passed && (
        <div className="flex items-center gap-2 text-[13px] text-brand-600 font-semibold">
          <RemixIcon name="ri-check-line" size={16} color="#C800DE" />
          <span>{result.message}</span>
        </div>
      )}

      {error && <p className="text-[12px] text-red-500">{error}</p>}

      {phase === 'running' && (
        <button
          onClick={() => { stopCamera(); setProgress({ done: 0, total: 0 }); setPhase(autoStart ? 'result' : 'consent') }}
          className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-neutral-200 bg-white text-neutral-700 text-[13px] font-semibold hover:bg-neutral-100 transition-colors"
        >
          Stop
        </button>
      )}

      {(phase === 'consent' || (phase === 'result' && !result?.passed)) && (
        <button
          onClick={() => void run()}
          disabled={consentRequired && !consent}
          className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-brand-500 text-white text-[13px] font-semibold hover:bg-brand-600 transition-colors disabled:opacity-60"
        >
          <RemixIcon name="ri-camera-line" size={15} color="#fff" />
          {phase === 'result' ? 'Try again' : 'Start liveness check'}
        </button>
      )}
    </div>
  )
}
