/// <reference lib="webworker" />
// Runs the faceliveness-web engine (WebAssembly) off the main thread — same role as
// face-liveness/demo/worker.js. In FOID it only drives the live face mesh and on-screen
// feedback; the SERVER runs the authoritative check and decides pass/fail.
import init, { Engine } from 'faceliveness-web'
import wasmUrl from 'faceliveness-web/liveness_wasm_bg.wasm?url'
import type { Challenge, SessionOptions } from 'faceliveness-web'

export type WorkerRequest =
  | { type: 'init' }
  | { type: 'start'; challenges: Challenge[]; options?: SessionOptions }
  | { type: 'frame'; pixels: ArrayBuffer; width: number; height: number; timestampMs: number }
  | { type: 'stop' }

let engine: Engine | null = null

self.onmessage = async ({ data: msg }: MessageEvent<WorkerRequest>) => {
  try {
    if (msg.type === 'init') {
      const t = performance.now()
      await init({ module_or_path: wasmUrl })
      self.postMessage({ type: 'ready', ms: performance.now() - t })
    } else if (msg.type === 'start') {
      engine?.free()
      engine = new Engine(msg.challenges, msg.options)   // loads the face models (a moment)
      self.postMessage({ type: 'started' })
    } else if (msg.type === 'frame') {
      if (!engine) return
      const t = performance.now()
      const result = engine.process(new Uint8Array(msg.pixels), {
        width: msg.width, height: msg.height, timestampMs: msg.timestampMs,
      })
      self.postMessage({ type: 'result', result, ms: performance.now() - t })
    } else if (msg.type === 'stop') {
      engine?.free()
      engine = null
    }
  } catch (error) {
    self.postMessage({ type: 'error', message: String((error as Error)?.message ?? error) })
  }
}
