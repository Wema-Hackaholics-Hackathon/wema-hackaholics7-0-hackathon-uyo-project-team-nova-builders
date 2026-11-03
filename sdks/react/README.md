# @foid/react — Continue with FOID for React

The browser side of **Continue with FOID**: a provider, a branded button, a hook and a framework-free core, in the style of `@react-oauth/google`. It opens the FOID popup with PKCE and hands you a one-time `code` to exchange **on your server** with [`foid`](../python) or [`@foid/node`](../node).

- Uses only your public **client ID**. No secrets, ever.
- `react` ≥ 17 as a peer dependency. No JSX and no build step inside; TypeScript types included.

## Install

Not on npm yet. Install from the FOID repository:

```bash
npm install ./sdks/react
```

## Quick start

```jsx
import { FoidProvider, ContinueWithFoid } from '@foid/react'

export default function SignUp() {
  return (
    <FoidProvider clientId="foid_app_test_…" foidUrl="https://app.foid.ng">
      <ContinueWithFoid
        scope="identity contact"
        onSuccess={({ code, codeVerifier }) =>
          fetch('/auth/foid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, codeVerifier }),
          })
        }
        onError={(e) => console.log(e.code)}   // popup_closed | access_denied | popup_blocked | state_mismatch
      />
    </FoidProvider>
  )
}
```

Your own button:

```jsx
import { useFoidLogin } from '@foid/react'

const login = useFoidLogin({ scope: 'identity', onSuccess, onError })
<button onClick={login} disabled={login.pending}>Log in with FOID</button>
```

No React:

```js
import { signInWithFoid } from '@foid/react/core'
const { code, codeVerifier } = await signInWithFoid({ clientId: 'foid_app_test_…', scope: 'identity' })
```

## API

| | |
|---|---|
| `<FoidProvider clientId foidUrl>` | Config for everything below. `foidUrl` defaults to `https://app.foid.ng`. |
| `<ContinueWithFoid>` | The button. Props: `onSuccess`, `onError`, `scope`, `nonce`, `state`, `codeChallenge`, `redirectUri`, `text` (`continue_with` · `signin_with` · `signup_with` · `verify_with`), `theme` (`filled` · `outline`), `size` (`large` · `medium` · `small`), `width`, `disabled`, `className`, `style` |
| `useFoidLogin(options)` | Returns `login()` (call from a click) with `login.pending` |
| `signInWithFoid(options)` | Framework-free popup sign-in → `{ code, state, codeVerifier }` |
| `handleRedirectCallback(search?)` | On your `redirectUri` page: finishes the no-popup fallback → `{ code, state, codeVerifier }` or `null` |
| `createPkcePair()` | `{ codeVerifier, codeChallenge }` if you want to hold the verifier |
| `FoidSignInError` | `.code`: `popup_closed`, `access_denied`, `popup_blocked`, `state_mismatch`, `missing_client_id`, `unknown` |

## Rules

- Only the client ID goes in the browser. Exchange the code on your server, once, within 60 seconds.
- Call `login()` / `signInWithFoid()` directly from a click handler so the popup isn't blocked.
- The popup only posts back to origins registered on your app (test apps: any `http://localhost` port).

## Docs

Full reference: the FOID docs site, page **SDKs → React** (`docs/sdks/react.md`; run `cd docs && pnpm dev` for http://localhost:5177/sdks/react). Try the real button at `/playground`. Working example: `demo/` (Harbor).
