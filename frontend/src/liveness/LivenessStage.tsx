/**
 * The camera stage of a liveness check — a port of face-liveness/demo (server-verified mode).
 *
 * Two loops run side by side, exactly like demo/app.js:
 *  - localLoop:  frames → Web Worker (faceliveness-web, WebAssembly) → live face mesh + stats.
 *                The local engine gets the server's challenges and no timeouts; it never decides.
 *  - serverLoop: frames (raw RGBA 320×240) → POST /api/v1/liveness/sessions/{nonce}/frame.
 *                The server runs the authoritative engine on its own clock; its status drives
 *                the prompts and the outcome, and it signs the receipt.
 * If the WebAssembly engine can't load, the check still works (server-only, no mesh).
 */
import { useEffect, useRef, useState } from 'react'
import RemixIcon from '@/components/RemixIcon'
import { BASE_URL } from '@/lib/api'
import type { Challenge } from 'faceliveness-web'
import type { WorkerRequest } from './liveness.worker'

const FRAME_W = 320
const FRAME_H = 240
const BRAND = '#C800DE'

export const PROMPTS: Record<string, string> = {
  blink: 'Blink',
  turn_left: 'Turn your head to your left',
  turn_right: 'Turn your head to your right',
  open_mouth: 'Open your mouth wide',
}
const CHIP: Record<string, string> = {
  blink: 'Blink', turn_left: 'Turn left', turn_right: 'Turn right', open_mouth: 'Open mouth',
}
export const FAILURES: Record<string, string> = {
  timeout: 'The check took too long.',
  step_timeout: "That step wasn't completed in time.",
  face_lost: 'Your face left the camera view.',
  multiple_faces: 'More than one face was in view.',
  spoof_suspected: 'The image looked like a photo or screen.',
}

export interface StartedSession {
  session_id: string
  challenges: string[]
}

export interface LivenessResult {
  passed: boolean
  message: string
  fail_reason?: string | null
}

interface ServerStatus {
  status: 'in_progress' | 'passed' | 'failed'
  done: boolean
  current_challenge: string | null
  remaining: number
  fail_reason: string | null
  face_count: number
}

type Phase = 'idle' | 'starting' | 'running' | 'finishing' | 'passed' | 'failed'

type WorkerReply =
  | { type: 'ready'; ms: number }
  | { type: 'started' }
  | { type: 'result'; result: { landmarks?: Array<[number, number]>; faceCount: number }; ms: number }
  | { type: 'error'; message: string }

function detail(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown; error?: { message?: string } } } })?.response?.data
  if (d?.error?.message) return d.error.message
  if (typeof d?.detail === 'string') return d.detail
  if (e instanceof Error && e.message) return e.message
  return fallback
}

export default function LivenessStage({
  start,
  complete,
  onFinished,
  autoStart = false,
}: {
  /** Ask the server for a new session (it picks the challenges). */
  start: () => Promise<StartedSession>
  /** Finalise the finished session on the server. */
  complete: (sessionId: string) => Promise<LivenessResult>
  onFinished?: (result: LivenessResult) => void
  autoStart?: boolean
}) {
  const videoRef   = useRef<HTMLVideoElement>(null)
  const overlayRef = useRef<HTMLCanvasElement>(null)
  const grabRef    = useRef<CanvasRenderingContext2D | null>(null)
  const workerRef  = useRef<Worker | null>(null)
  const readyRef   = useRef<Promise<boolean> | null>(null)
  const pending    = useRef(new Map<string, (data: WorkerReply) => void>())
  const runRef     = useRef<{ done: boolean; nonce: string; startedAt: number; stream: MediaStream | null } | null>(null)

  const [phase, setPhase]           = useState<Phase>('idle')
  const [prompt, setPrompt]         = useState('')
  const [challenges, setChallenges] = useState<string[]>([])
  const [remaining, setRemaining]   = useState(0)
  const [result, setResult]         = useState<LivenessResult | null>(null)
  const [meshOn, setMeshOn]         = useState(false)
  const [note, setNote]             = useState('')

  /* ── worker: start loading the engine as soon as the stage mounts ─────── */
  useEffect(() => {
    const worker = new Worker(new URL('./liveness.worker.ts', import.meta.url), { type: 'module' })
    workerRef.current = worker
    worker.onmessage = ({ data }: MessageEvent<WorkerReply>) => {
      if (data.type === 'error') {
        // release every waiter so no loop hangs; the check carries on server-only
        for (const resolve of pending.current.values()) resolve(data)
        pending.current.clear()
        return
      }
      pending.current.get(data.type)?.(data)
    }
    readyRef.current = new Promise<boolean>(resolve => {
      const timer = setTimeout(() => resolve(false), 45_000)     // slow networks: carry on without the mesh
      pending.current.set('ready', reply => { clearTimeout(timer); resolve(reply.type === 'ready') })
      worker.postMessage({ type: 'init' } satisfies WorkerRequest)
    })
    return () => {
      if (runRef.current) runRef.current.done = true
      runRef.current?.stream?.getTracks().forEach(t => t.stop())
      worker.terminate()
    }
  }, [])

  useEffect(() => {
    if (autoStart) void begin()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function ask(msg: WorkerRequest, reply: WorkerReply['type']): Promise<WorkerReply> {
    return new Promise(resolve => {
      pending.current.set(reply, resolve)
      const transfer = msg.type === 'frame' ? [msg.pixels] : []
      workerRef.current?.postMessage(msg, transfer)
    })
  }

  function grabFrame(): ArrayBuffer {
    if (!grabRef.current) {
      const c = document.createElement('canvas')
      c.width = FRAME_W
      c.height = FRAME_H
      grabRef.current = c.getContext('2d', { willReadFrequently: true })
    }
    const ctx = grabRef.current!
    ctx.drawImage(videoRef.current!, 0, 0, FRAME_W, FRAME_H)
    return ctx.getImageData(0, 0, FRAME_W, FRAME_H).data.buffer
  }

  function drawMesh(points?: Array<[number, number]>) {
    const ctx = overlayRef.current?.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, FRAME_W, FRAME_H)
    if (!points) return
    ctx.fillStyle = 'rgba(200, 0, 222, 0.85)'
    for (const [x, y] of points) ctx.fillRect(x - 0.6, y - 0.6, 1.2, 1.2)
  }

  /* ── the check ──────────────────────────────────────────────────────── */
  async function begin() {
    setResult(null)
    setNote('')
    setPhase('starting')
    setPrompt('Starting camera…')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' }, audio: false,
      })
      videoRef.current!.srcObject = stream
      await videoRef.current!.play()
    } catch {
      return end({ passed: false, message: 'Camera access is needed. Allow it in your browser settings and try again.' })
    }

    let session: StartedSession
    try {
      setPrompt('Preparing your check…')
      session = await start()
    } catch (e) {
      stream.getTracks().forEach(t => t.stop())
      return end({ passed: false, message: detail(e, 'Could not start the liveness check.') })
    }
    runRef.current = { done: false, nonce: session.session_id, startedAt: performance.now(), stream }
    setChallenges(session.challenges)
    setRemaining(session.challenges.length)

    // Live face mesh (optional): same challenges, no local timeouts — the server decides.
    setPrompt('Loading face models…')
    const meshReady = await readyRef.current
    let meshOk = !!meshReady
    if (meshOk) {
      const reply = await ask({ type: 'start', challenges: session.challenges as Challenge[],
                                options: { totalTimeoutMs: 1e12, stepTimeoutMs: 1e12, faceLostMs: 1e12 } }, 'started')
      meshOk = reply.type === 'started'
    }
    setMeshOn(meshOk)
    if (runRef.current.done) return

    setPrompt(PROMPTS[session.challenges[0]] ?? 'Look at the camera')
    setPhase('running')
    if (meshOk) void localLoop()
    void serverLoop()
  }

  async function localLoop() {
    while (runRef.current && !runRef.current.done) {
      const run = runRef.current
      const reply = await ask({
        type: 'frame', pixels: grabFrame(), width: FRAME_W, height: FRAME_H,
        timestampMs: Math.round(performance.now() - run.startedAt),
      }, 'result')
      if (run.done) break
      if (reply.type !== 'result') { setMeshOn(false); drawMesh(); break }   // engine error → server-only
      drawMesh(reply.result.landmarks)
    }
  }

  async function serverLoop() {
    while (runRef.current && !runRef.current.done) {
      const run = runRef.current
      let status: ServerStatus
      try {
        const res = await fetch(`${BASE_URL}/api/v1/liveness/sessions/${run.nonce}/frame?w=${FRAME_W}&h=${FRAME_H}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream' },
          body: grabFrame(),
        })
        if (res.status === 429) continue          // previous frame still processing
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(typeof body.detail === 'string' ? body.detail : `Server error ${res.status}`)
        }
        status = await res.json()
      } catch (e) {
        return finish(null, detail(e, 'Lost connection to the server.'))
      }
      if (run.done) return
      if (status.done) return finish(status)
      setRemaining(status.remaining)
      if (status.face_count === 0) setNote('Move your face into the frame')
      else if (status.face_count > 1) setNote('Only one face should be in view')
      else setNote('')
      setPrompt(PROMPTS[status.current_challenge ?? ''] ?? 'Look at the camera')
    }
  }

  async function finish(status: ServerStatus | null, error?: string) {
    const run = runRef.current
    if (!run || run.done) return
    run.done = true
    run.stream?.getTracks().forEach(t => t.stop())
    workerRef.current?.postMessage({ type: 'stop' } satisfies WorkerRequest)
    drawMesh()
    if (error) return end({ passed: false, message: error })
    setRemaining(0)
    setPhase('finishing')
    setPrompt(status?.status === 'passed' ? 'Checking your face…' : 'Finishing…')
    try {
      const res = await complete(run.nonce)
      end(res.passed ? res : { ...res, message: FAILURES[res.fail_reason ?? ''] ?? res.message })
    } catch (e) {
      end({ passed: false, message: detail(e, 'Could not complete the check.') })
    }
  }

  function end(res: LivenessResult) {
    setResult(res)
    setPhase(res.passed ? 'passed' : 'failed')
    onFinished?.(res)
  }

  /* ── UI ─────────────────────────────────────────────────────────────── */
  const current = challenges.length - remaining
  const live = phase === 'starting' || phase === 'running' || phase === 'finishing'

  return (
    <div className="flex flex-col gap-3">
      <div className={[
        'relative w-full aspect-[4/3] rounded-2xl overflow-hidden bg-neutral-900',
        live ? '' : 'hidden',
      ].join(' ')}>
        {/* Shown mirrored, like a mirror; frames are sent un-mirrored (demo/style.css). */}
        <video ref={videoRef} playsInline muted className="absolute inset-0 w-full h-full object-cover" style={{ transform: 'scaleX(-1)' }} />
        <canvas ref={overlayRef} width={FRAME_W} height={FRAME_H}
          className="absolute inset-0 w-full h-full object-cover pointer-events-none" style={{ transform: 'scaleX(-1)' }} />
        {/* framing guide */}
        <svg viewBox="0 0 320 240" className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="xMidYMid slice">
          <ellipse cx="160" cy="118" rx="74" ry="96" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="2" strokeDasharray="6 6" />
        </svg>
        <div className="absolute inset-x-0 bottom-0 px-4 pt-10 pb-4 bg-gradient-to-t from-black/80 to-transparent text-center">
          <div className="text-white text-[18px] sm:text-[20px] font-bold leading-tight">{prompt}</div>
          {note && <div className="text-amber-200 text-[12.5px] mt-1">{note}</div>}
        </div>
        {phase === 'running' && !meshOn && (
          <div className="absolute top-3 left-3 text-[10.5px] text-white/70 bg-black/40 rounded-full px-2 py-0.5">server check</div>
        )}
      </div>

      {challenges.length > 0 && live && (
        <ol className="flex flex-wrap gap-2 justify-center">
          {challenges.map((c, i) => {
            const done = i < current
            const isCurrent = i === current && phase === 'running'
            return (
              <li key={`${c}-${i}`}
                className={[
                  'flex items-center gap-1 px-3 py-1.5 rounded-full text-[12px] font-semibold transition-colors',
                  done ? 'bg-[#fae8ff] text-[#a21caf]' : isCurrent ? 'text-white' : 'bg-neutral-100 text-neutral-500',
                ].join(' ')}
                style={isCurrent ? { background: BRAND } : undefined}
              >
                {done && <RemixIcon name="ri-check-line" size={13} color="#a21caf" />}
                {CHIP[c] ?? c}
              </li>
            )
          })}
        </ol>
      )}

      {phase === 'idle' && (
        <button onClick={() => void begin()}
          className="flex items-center justify-center gap-2 py-3 rounded-xl text-white text-[14px] font-bold hover:opacity-90"
          style={{ background: BRAND }}>
          <RemixIcon name="ri-camera-line" size={17} color="#fff" /> Start camera
        </button>
      )}

      {(phase === 'passed' || phase === 'failed') && result && (
        <div className={[
          'flex flex-col items-center text-center gap-2 py-5 px-4 rounded-2xl',
          phase === 'passed' ? 'bg-[#fdf4ff]' : 'bg-red-50',
        ].join(' ')}>
          <RemixIcon name={phase === 'passed' ? 'ri-checkbox-circle-fill' : 'ri-error-warning-line'} size={34}
            color={phase === 'passed' ? BRAND : '#dc2626'} />
          <div className={`text-[15px] font-bold ${phase === 'passed' ? 'text-neutral-900' : 'text-red-600'}`}>
            {phase === 'passed' ? 'Liveness confirmed' : 'Check not completed'}
          </div>
          <div className="text-[13px] text-neutral-600">{result.message}</div>
          {phase === 'failed' && (
            <button onClick={() => void begin()}
              className="mt-1 px-5 py-2 rounded-full text-white text-[13px] font-bold hover:opacity-90"
              style={{ background: BRAND }}>
              Try again
            </button>
          )}
        </div>
      )}
    </div>
  )
}
