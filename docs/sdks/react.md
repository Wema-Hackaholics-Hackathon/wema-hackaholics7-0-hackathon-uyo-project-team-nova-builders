# React SDK — `@foid/react`

The browser side of [Continue with FOID](/guide/continue-with-foid), in the style of `@react-oauth/google`: a provider, a branded button, a hook, and a framework-free core. It opens the FOID popup with PKCE, checks the response, and hands you a one-time `code` and `codeVerifier` to send to **your server**, which exchanges them with the [Python](./python) or [Node](./node) SDK.

It only ever uses your public **client ID**. It never sees a secret, and you should never exchange the code in the browser.

```bash
npm install ./sdks/react   # see SDKs → Install; not on npm yet
```

`react` (≥ 17) is a peer dependency. The package has no JSX and no build step.

<FoidPlayground compact />

Every option, with live code, in the [Playground](/playground).

## Quick start

```jsx
import { FoidProvider, ContinueWithFoid } from '@foid/react'

export default function SignUp() {
  return (
    <FoidProvider clientId="foid_app_test_…" foidUrl="https://usefoid.pages.dev">
      <ContinueWithFoid
        scope="identity contact"
        onSuccess={({ code, codeVerifier }) =>
          fetch('/auth/foid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, codeVerifier }),
          })
        }
        onError={(e) => console.log(e.code)}
      />
    </FoidProvider>
  )
}
```

## `<FoidProvider>`

```jsx
<FoidProvider clientId="foid_app_live_…" foidUrl="https://usefoid.pages.dev">…</FoidProvider>
```

| Prop | |
|---|---|
| `clientId` | Required. Your sign-in app's public client ID. |
| `foidUrl` | The FOID web app that hosts the popup. Default `https://usefoid.pages.dev`; `http://localhost:5173` when running FOID locally. |

Put it once near the root (or around the part of the page with the button). `useFoidLogin` and `<ContinueWithFoid>` throw if they're used outside it.

## `<ContinueWithFoid>`

The FOID-branded button. It shows the FOID mark and "Waiting for FOID…" while the popup is open.

| Prop | Default | |
|---|---|---|
| `onSuccess` | — | `({ code, state, codeVerifier }) => void`. Send `code` and `codeVerifier` to your server. |
| `onError` | — | `(error: FoidSignInError) => void`. See [errors](#errors). |
| `scope` | `"profile"` | Space-separated: `profile` (always included), `identity`, `contact`, `liveness`, `financial`. Can't exceed the app's registered scopes. |
| `nonce` | — | Echoed back as `result.nonce` from the exchange, so you can bind the sign-in to a session. |
| `state` | random | Your own `state`. By default a random one is made and checked for you. |
| `codeChallenge` | — | Your own PKCE challenge (S256), when your server holds the verifier. `codeVerifier` then comes back `null`. |
| `redirectUri` | — | Fallback when the popup is blocked: the page navigates to FOID and returns here. Must be registered on the app (any localhost URL in test). |
| `text` | `"continue_with"` | `continue_with`, `signin_with`, `signup_with`, `verify_with`: "Continue with / Sign in with / Sign up with / Verify with FOID". |
| `theme` | `"filled"` | `filled` (purple) or `outline` (white with a border). |
| `size` | `"large"` | `large` (44 px), `medium` (38 px), `small` (32 px). |
| `width` | auto | Any CSS width, e.g. `260` or `"100%"`. |
| `disabled` | `false` | |
| `className`, `style` | — | Applied to the `<button>`, which also carries a `data-foid-button` attribute for styling. |

## `useFoidLogin(options)`

For your own button. It takes the same sign-in options (`scope`, `nonce`, `state`, `codeChallenge`, `redirectUri`, `onSuccess`, `onError`) and returns a function to call **from a click handler**. The function also has a `pending` property.

```jsx
import { useFoidLogin } from '@foid/react'

function LoginButton() {
  const login = useFoidLogin({
    scope: 'identity',
    onSuccess: ({ code, codeVerifier }) => sendToServer(code, codeVerifier),
    onError: (e) => setError(e.code),
  })
  return <button onClick={login} disabled={login.pending}>Log in with FOID</button>
}
```

Call it directly in the click handler, not after an `await`, or the browser may block the popup.

## Core (no React) — `@foid/react/core`

```js
import { signInWithFoid, createPkcePair, handleRedirectCallback, FoidSignInError } from '@foid/react/core'
```

These are also re-exported from `@foid/react`.

### `signInWithFoid(options)`

```js
button.addEventListener('click', async () => {
  try {
    const { code, state, codeVerifier } = await signInWithFoid({
      clientId: 'foid_app_test_…',
      foidUrl: 'https://usefoid.pages.dev',
      scope: 'identity',
    })
    await sendToServer(code, codeVerifier)
  } catch (e) {
    console.log(e.code)   // FoidSignInError
  }
})
```

Options: `clientId` (required), `foidUrl`, `scope`, `nonce`, `state`, `codeChallenge`, `redirectUri`, `width` (default 460) and `height` (default 720) for the popup window.

What it does:

1. Opens a popup **synchronously**, so call it straight from a click.
2. Creates a PKCE pair (unless you passed `codeChallenge`) and a random `state`.
3. Points the popup at `{foidUrl}/oauth/authorize?…&response_mode=web_message&origin=<your origin>`.
4. Resolves with `{ code, state, codeVerifier }` when FOID posts back. It only accepts messages from the FOID origin and the popup it opened, with a matching `state`.

If the popup is blocked and you passed `redirectUri`, it stores the state and verifier in `sessionStorage` and navigates the page to FOID with `response_mode=query`. The returned promise never settles, because the page is leaving. Finish on the redirect page with `handleRedirectCallback()`.

### `handleRedirectCallback(search = window.location.search)`

Call it on your `redirectUri` page. It returns `{ code, state, codeVerifier }` when this page load is a FOID return, or `null` otherwise. It throws `FoidSignInError` with `state_mismatch` or `access_denied` (or the error FOID returned). It clears the stored state, so call it once per page load and then clean the URL.

```js
const result = handleRedirectCallback()
if (result) {
  history.replaceState({}, '', location.pathname)   // drop ?code=&state=
  await sendToServer(result.code, result.codeVerifier, location.origin + location.pathname)
}
```

Your server must pass the same `redirect_uri` to the exchange in redirect mode.

### `createPkcePair()`

Resolves to `{ codeVerifier, codeChallenge }` (S256, made with Web Crypto). Use it when you want to hold the verifier yourself and pass only `codeChallenge` to `signInWithFoid`. Make the pair **before** the click, so the popup still opens synchronously.

## Errors {#errors}

`onError` and rejected promises receive a `FoidSignInError` with a `code`:

| `code` | Meaning |
|---|---|
| `popup_closed` | The person closed the FOID window. This is also what you see if the popup showed a setup error (unknown client ID, origin not allowed, scope not allowed) and they closed it. |
| `access_denied` | The person pressed Cancel or declined. |
| `popup_blocked` | The popup was blocked and there's no `redirectUri`. |
| `state_mismatch` | The response didn't match this sign-in, so it was ignored. |
| `missing_client_id` | No `clientId`. |
| `unknown` | Anything unexpected (`<ContinueWithFoid>` / `useFoidLogin` wrap it). |

Errors from the code exchange (`invalid_grant`, `invalid_client`) happen on your server. See the [server SDKs](./node#errors).

## Notes

- **Only the client ID** belongs in the browser. Exchange codes on your server, once, within 60 seconds.
- **Origins:** the popup only posts the code back to an origin registered on the app (test apps: any `http://localhost` port).
- **Next.js / SSR:** the button and hook only touch `window` when clicked, so they render on the server. Call `handleRedirectCallback` in an effect or a client component.
- **TypeScript:** types are in `index.d.ts` and `core.d.ts`.
