// Continue with FOID — React bindings (in the style of @react-oauth/google). No JSX, no build step.
import { createContext, createElement, useCallback, useContext, useState } from 'react'
import { DEFAULT_FOID_URL, FoidSignInError, handleRedirectCallback, signInWithFoid } from './core.js'

export { createPkcePair, handleRedirectCallback, signInWithFoid, FoidSignInError } from './core.js'

const Ctx = createContext(null)

/** <FoidProvider clientId="foid_app_live_…"> around your app (or the part with the button). */
export function FoidProvider({ clientId, foidUrl = DEFAULT_FOID_URL, children }) {
  return createElement(Ctx.Provider, { value: { clientId, foidUrl } }, children)
}

function useConfig() {
  const c = useContext(Ctx)
  if (!c) throw new Error('Wrap your app in <FoidProvider clientId="…">')
  return c
}

/**
 * const login = useFoidLogin({ scope: 'identity contact', onSuccess: ({ code, codeVerifier }) => …, onError })
 * <button onClick={login}>…</button>   — call it from a click (popup blockers)
 */
export function useFoidLogin({ scope = 'profile', nonce, state, codeChallenge, redirectUri, onSuccess, onError } = {}) {
  const { clientId, foidUrl } = useConfig()
  const [pending, setPending] = useState(false)
  const login = useCallback(() => {
    setPending(true)
    signInWithFoid({ clientId, foidUrl, scope, nonce, state, codeChallenge, redirectUri })
      .then((r) => onSuccess?.(r), (e) => onError?.(e instanceof FoidSignInError ? e : new FoidSignInError('unknown', String(e))))
      .finally(() => setPending(false))
  }, [clientId, foidUrl, scope, nonce, state, codeChallenge, redirectUri, onSuccess, onError])
  login.pending = pending
  return login
}

const MARK = createElement('svg', { width: 18, height: 18, viewBox: '0 0 24 24', 'aria-hidden': true },
  createElement('rect', { width: 24, height: 24, rx: 6, fill: 'currentColor' }),
  createElement('path', { d: 'M8 6.5h8.5v2.6h-5.6v2.2h4.8v2.5h-4.8v3.7H8z', fill: 'var(--foid-mark-ink, #fff)' }))

const LABELS = { continue_with: 'Continue with FOID', signin_with: 'Sign in with FOID', signup_with: 'Sign up with FOID', verify_with: 'Verify with FOID' }

/** The branded button. Props: onSuccess, onError, scope, text, theme ('filled' | 'outline'), size, width, disabled, … */
export function ContinueWithFoid({
  onSuccess, onError, scope, nonce, state, codeChallenge, redirectUri,
  text = 'continue_with', theme = 'filled', size = 'large', width, disabled, className, style,
}) {
  const login = useFoidLogin({ scope, nonce, state, codeChallenge, redirectUri, onSuccess, onError })
  const filled = theme === 'filled'
  const h = size === 'small' ? 32 : size === 'medium' ? 38 : 44
  return createElement('button', {
    type: 'button', onClick: login, disabled: disabled || login.pending, className, 'data-foid-button': '',
    style: {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 10, height: h, width,
      padding: '0 18px', borderRadius: 999, font: `600 ${size === 'small' ? 13 : 14.5}px system-ui, sans-serif`,
      cursor: disabled || login.pending ? 'default' : 'pointer', opacity: disabled ? 0.6 : 1,
      border: filled ? 'none' : '1px solid #e4e4e7', background: filled ? '#C800DE' : '#fff',
      color: filled ? '#fff' : '#18181b', '--foid-mark-ink': filled ? '#C800DE' : '#fff', ...style,
    },
  }, createElement('span', { style: { color: filled ? '#fff' : '#C800DE', display: 'inline-flex' } }, MARK),
     login.pending ? 'Waiting for FOID…' : LABELS[text] ?? LABELS.continue_with)
}

