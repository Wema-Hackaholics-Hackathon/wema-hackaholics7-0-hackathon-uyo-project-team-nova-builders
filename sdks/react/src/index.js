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

// The FOID mark (two slanted bars), traced from the official logo. Takes the text colour.
const MARK_PATH = 'M60.9 0.0 59.1 0.0 58.6 0.7 55.7 1.8 7.4 16.4 6.4 17.0 5.6 18.0 3.2 44.2 3.4 46.2 4.4 46.8 30.8 38.8 37.4 35.7 42.9 31.9 46.1 29.2 51.0 23.9 56.4 15.8 57.8 13.1 59.8 7.9 60.9 2.9ZM39.4 40.4 37.8 40.3 4.2 50.6 3.0 51.5 2.3 54.1 0.9 70.9 0.5 72.8 0.0 73.6 0.0 81.2 10.9 77.9 15.9 75.5 21.5 71.8 27.3 66.4 32.2 60.4 36.1 53.6 37.7 50.1 38.9 46.4 39.9 42.0 39.8 40.9Z'
const MARK = createElement('svg', { height: 18, width: 14, viewBox: '0 0 62 82', 'aria-hidden': true, focusable: 'false' },
  createElement('path', { d: MARK_PATH, fill: 'currentColor' }))

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
      color: filled ? '#fff' : '#18181b', ...style,
    },
  }, createElement('span', { style: { color: filled ? '#fff' : '#C800DE', display: 'inline-flex' } }, MARK),
     login.pending ? 'Waiting for FOID…' : LABELS[text] ?? LABELS.continue_with)
}

