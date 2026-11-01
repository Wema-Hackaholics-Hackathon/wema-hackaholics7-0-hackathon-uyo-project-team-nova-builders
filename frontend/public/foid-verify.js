/*!
 * FOID Verify — drop-in hosted verification (liveness, NIN, BVN) for your web app.
 *
 *   <script src="https://<foid-app>/foid-verify.js"></script>
 *   <script>
 *     // client_token comes from YOUR server: POST /api/open/v1/verifications
 *     FoidVerify.open({
 *       clientToken: 'vs_...',
 *       onComplete: function (r) { console.log(r.verification_id, r.outcome) },  // then confirm server-side
 *       onCancel:   function (r) { },
 *       onClose:    function ()  { },
 *     })
 *   </script>
 *
 * The result passed to onComplete is a convenience only — always confirm with the
 * `verification.completed` webhook or GET /api/open/v1/verifications/{id} on your server.
 * Mobile apps (React Native / Flutter / native): open the `hosted_url` in a WebView
 * with camera permission instead of using this script.
 */
(function () {
  'use strict'

  var script = document.currentScript
  var DEFAULT_ORIGIN = script && script.src ? new URL(script.src).origin : window.location.origin
  var active = null

  function close() {
    if (!active) return
    window.removeEventListener('message', active.onMessage)
    document.removeEventListener('keydown', active.onKey)
    active.overlay.remove()
    document.body.style.overflow = active.prevOverflow
    var cb = active.onClose
    active = null
    if (cb) cb()
  }

  function open(opts) {
    opts = opts || {}
    if (active) close()
    var origin = (opts.origin || DEFAULT_ORIGIN).replace(/\/$/, '')
    var url = opts.url || (opts.clientToken ? origin + '/verify/' + encodeURIComponent(opts.clientToken) : null)
    if (!url) throw new Error('FoidVerify.open: pass clientToken (or url)')
    var expectedOrigin = new URL(url).origin

    var overlay = document.createElement('div')
    overlay.setAttribute('role', 'dialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.setAttribute('aria-label', 'Identity verification by FOID')
    overlay.style.cssText =
      'position:fixed;inset:0;z-index:2147483646;background:rgba(17,17,23,.55);' +
      'display:flex;align-items:center;justify-content:center;padding:12px;'

    var frame = document.createElement('iframe')
    frame.src = url
    frame.title = 'FOID identity verification'
    frame.allow = 'camera; fullscreen'
    frame.style.cssText =
      'width:100%;max-width:460px;height:min(760px,100%);border:0;border-radius:16px;' +
      'background:#fafafa;box-shadow:0 20px 60px rgba(0,0,0,.35);'

    var closeBtn = document.createElement('button')
    closeBtn.type = 'button'
    closeBtn.setAttribute('aria-label', 'Close verification')
    closeBtn.textContent = '×'
    closeBtn.style.cssText =
      'position:absolute;top:10px;right:14px;width:36px;height:36px;border-radius:50%;border:0;' +
      'background:#fff;color:#18181b;font:600 22px/36px system-ui,sans-serif;cursor:pointer;'
    closeBtn.onclick = close

    overlay.appendChild(frame)
    overlay.appendChild(closeBtn)
    document.body.appendChild(overlay)

    function onMessage(e) {
      if (e.origin !== expectedOrigin || !e.data || e.data.source !== 'foid') return
      var result = {
        verification_id: e.data.verification_id,
        status: e.data.status,
        outcome: e.data.outcome,
      }
      if (e.data.type === 'verification.completed') {
        if (opts.onComplete) opts.onComplete(result)
        setTimeout(close, 1200)
      } else if (e.data.type === 'verification.cancelled') {
        if (opts.onCancel) opts.onCancel(result)
        setTimeout(close, 1200)
      }
    }
    function onKey(e) { if (e.key === 'Escape') close() }

    active = {
      overlay: overlay,
      onMessage: onMessage,
      onKey: onKey,
      onClose: opts.onClose,
      prevOverflow: document.body.style.overflow,
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('message', onMessage)
    document.addEventListener('keydown', onKey)
  }

  window.FoidVerify = { open: open, close: close, version: '1.0.0' }
})()
