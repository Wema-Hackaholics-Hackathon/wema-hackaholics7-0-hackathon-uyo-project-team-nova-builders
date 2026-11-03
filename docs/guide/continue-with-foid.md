# Continue with FOID

A sign-in button, like "Sign in with Google", where the person arrives **already verified**. They approve what to share on FOID's own screen, and your server gets their verified details, never a raw NIN or BVN.

Under the hood it's OAuth 2.0 authorization code with PKCE: the browser gets a one-time **code**, and your **server** exchanges it for the result using credentials only your server has.

Try the real button. It uses FOID's own test app for these docs:

<FoidPlayground compact />

More options (labels, themes, sizes, scopes) and the matching code are in the [Playground](/playground).

## How it works

```
Your page                FOID popup                         Your server                 FOID API
─────────                ──────────                         ───────────                 ────────
<ContinueWithFoid> ──▶  email + one-time code
  (client ID, PKCE)      consent screen ("Acme wants…")
                         face check (live, first time)
        ◀── code ─────── postMessage to your origin
        ── code + verifier ──────────────────────────────▶  foid.oauth.exchange() ──▶  POST /oauth/token
                                                                                ◀──  the person's result
```

1. The button opens a FOID popup with your **client ID**, the scopes you ask for, and a PKCE challenge.
2. The person enters their email and the 6-digit code FOID emails them. No password.
3. FOID shows a consent screen listing your business and each scope. In live mode, the first time they share with you, they also do a ~5-second face check that is matched against their enrolled FOID face.
4. The popup posts a one-time `code` back to your page, and only to your registered origin.
5. Your page sends `code` and `codeVerifier` to your server. Your server exchanges them **once, within 60 seconds**, with its client secret or key pair.
6. The result tells you who signed in and what they shared. Store `subject_id` on your user.

## 1. Register a sign-in app

In the console, open **Sign-in apps**, then **Create app**, and choose Test or Live:

| Field | Notes |
|---|---|
| Name | Shown to the person on FOID's consent screen. |
| Allowed origins | Where the button runs, as scheme + host (+ port), e.g. `https://app.acme.com`. Popup results are only posted to these origins. |
| Redirect URIs | For the no-popup fallback, exact match, e.g. `https://app.acme.com/auth/foid/callback`. |
| Scopes | The most this app may ask for: `identity`, `contact`, `liveness`, `financial`. `profile` (name) is always included. |

**Test apps** also accept `http://localhost:<any port>` and `http://127.0.0.1:<any port>` without registering them. **Live apps** need `https://` and exact matches. Up to 10 apps per environment, and up to 10 origins and 10 redirect URIs per app.

You get:

- a **client ID** (`foid_app_test_…`), which is public and goes in your front end;
- a **client secret** (`foid_cs_test_…`), shown **once**, which stays on your server. You can rotate it (the old one keeps working for 24 hours) or revoke it.

Or use a [key pair](#key-pair-private-key-jwt) instead of a secret.

## 2. Add the button

With React, use [`@foid/react`](/sdks/react):

```jsx
import { FoidProvider, ContinueWithFoid } from '@foid/react'

export default function App() {
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

- `foidUrl` is the FOID web app that hosts the popup (`http://localhost:5173` when running FOID locally).
- `scope` is space-separated. Ask only for what you need; the app's registered scopes are the ceiling.
- Prefer your own button? Use `useFoidLogin()`. No React? `signInWithFoid()` from `@foid/react/core`. See [React SDK](/sdks/react).

The SDK creates the PKCE pair and a random `state` in the browser, checks that the response's `state` matches, and only accepts messages from the FOID origin and the popup it opened.

## 3. Exchange the code on your server

::: code-group

```js [Node]
import express from 'express'
import { Foid } from '@foid/node'

const foid = new Foid({
  clientId: process.env.FOID_CLIENT_ID,
  clientSecret: process.env.FOID_CLIENT_SECRET,
  baseUrl: 'https://api.foid.ng',
})

const app = express()
app.use(express.json())

app.post('/auth/foid', async (req, res) => {
  const { code, codeVerifier } = req.body
  const person = await foid.oauth.exchange(code, codeVerifier)
  // Link or create your user by person.subject_id, then start your own session.
  res.json({ name: `${person.subject.first_name} ${person.subject.last_name}` })
})
```

```python [Python]
import os
from fastapi import FastAPI
from foid import Foid

foid = Foid(client_id=os.environ["FOID_CLIENT_ID"],
            client_secret=os.environ["FOID_CLIENT_SECRET"],
            base_url="https://api.foid.ng")
app = FastAPI()

@app.post("/auth/foid")
def sign_in(body: dict):
    person = foid.oauth.exchange(body["code"], body["codeVerifier"])
    # Link or create your user by person["subject_id"], then start your own session.
    return {"name": f'{person["subject"]["first_name"]} {person["subject"]["last_name"]}'}
```

```bash [curl]
curl https://api.foid.ng/api/open/v1/oauth/token \
  -u "$FOID_CLIENT_ID:$FOID_CLIENT_SECRET" \
  -d grant_type=authorization_code \
  -d code="$CODE" \
  -d code_verifier="$CODE_VERIFIER"
```

:::

The token endpoint accepts a form or JSON body, with the client secret as HTTP Basic (recommended) or as `client_id` + `client_secret` fields. Full details: [`POST /oauth/token`](/api/reference#post-oauth-token).

Rules for the code:

- **Single use** and valid for **60 seconds**.
- Bound to your client ID, the PKCE verifier and, in redirect mode, the exact `redirect_uri`.
- **A second exchange of the same code revokes the grant** it created. FOID treats a reused code as leaked, cancels that sign-in, and posts an alert in your console. Make sure your server exchanges each code exactly once.

## The result

```json
{
  "object": "foid_sign_in",
  "env": "test",
  "sandbox": true,
  "nonce": "n_51b7",
  "subject_id": "ce669b19-ced4-4ff9-ac99-01d560450380",
  "scopes": ["contact", "identity", "profile"],
  "foid_account": true,
  "face_rematched_at": null,
  "subject": {
    "id": "ce669b19-ced4-4ff9-ac99-01d560450380",
    "customer_ref": null,
    "env": "test",
    "consent": { "status": "active", "scopes": ["contact", "identity", "profile"] },
    "has_foid_account": true,
    "created_at": "2026-11-03T20:25:02.497513+00:00",
    "first_name": "Chiamaka",
    "middle_name": null,
    "last_name": "Eze",
    "date_of_birth": "1990-01-01",
    "nin": { "verified": true, "last4": "0001" },
    "bvn": { "verified": true, "last4": "0002" },
    "email": "sandbox.person@example.com",
    "phone": "**********0001"
  },
  "checks": []
}
```

| Field | Meaning |
|---|---|
| `subject_id` | Stable ID for this person at your business. Store it on your user; the same person signing in again gets the same ID. |
| `subject` | What the granted scopes allow: `profile` gives the name; `identity` adds date of birth and `nin` / `bvn` (`verified`, `last4`); `contact` adds email and a masked phone; `liveness` adds `liveness.passed_at`. |
| `scopes` | What the person approved. `profile` is always there. |
| `checks` | Check results on file for this subject (with `identity` or `liveness`). |
| `foid_account` | `true` if the person has a FOID account. False for a new person who chose not to save to FOID. |
| `face_rematched_at` | When the person passed the fresh face re-match for this sign-in (live), else `null`. |
| `nonce` | The `nonce` you passed when starting sign-in. Compare it to detect a replayed sign-in. |
| `sandbox` / `env` | `true` / `test` for a test app. In test mode only the name is real. |

Reading the person again later uses your **API key**, for example [`GET /subjects/{id}`](/api/reference#get-subjects-subject-id), and still goes through their consent. If they revoke, you get `403 consent_revoked`. The client secret never becomes a standing data key.

## Redirect fallback (no popup)

If the browser blocks the popup and you passed `redirectUri`, the SDK navigates the whole page to FOID instead (`response_mode=query`). FOID sends the person back to your redirect URI with `?code=…&state=…`. On that page:

```js
import { handleRedirectCallback } from '@foid/react/core'

const result = handleRedirectCallback()   // null if this page load isn't a FOID return
if (result) {
  await fetch('/auth/foid', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: result.code, codeVerifier: result.codeVerifier, redirectUri: location.origin + '/auth/foid/callback' }),
  })
}
```

In redirect mode, your server must pass the **same** `redirect_uri` to the exchange (`redirect_uri=` in Python, `{ redirectUri }` in Node). The redirect URI must be registered on the app (test apps: any localhost URL works).

## Server-led sign-in

You can also create the PKCE pair on your server with the SDK's `create_pkce()` / `createPkce()`, keep the verifier, state and nonce server-side, and send the browser to:

```
{foidUrl}/oauth/authorize?client_id=…&scope=profile%20identity&state=…&nonce=…
  &code_challenge=…&code_challenge_method=S256
  &response_mode=query&redirect_uri=https://app.acme.com/auth/foid/callback
```

Use `response_mode=web_message&origin=https://app.acme.com` to get the code by `postMessage` in a popup instead. The [Harbor example app](/sdks/example-app) does both.

## Key pair (private_key_jwt) {#key-pair-private-key-jwt}

Recommended for banks: instead of a client secret, your server holds a **private key** and signs each exchange. FOID only stores the public key, so there is no secret on FOID's side to leak.

1. Generate a key pair with either SDK. Each writes `foid_private_key.pem` and prints the public JWK:
   ```bash
   python -m foid keygen      # pip install 'foid[keypair]'
   npx foid keygen            # from @foid/node
   ```
2. In the console, open **Sign-in apps**, click **Edit** on the app, choose **Key pair**, paste the public JWK and save. An app uses a key pair **or** client secrets, not both.
3. Pass the private key instead of the secret:

::: code-group

```js [Node]
import { readFileSync } from 'node:fs'
const foid = new Foid({
  clientId: process.env.FOID_CLIENT_ID,
  privateKeyPem: readFileSync('foid_private_key.pem', 'utf8'),
  keyId: 'a1b2c3d4',   // the "kid" from the public JWK (optional)
})
```

```python [Python]
foid = Foid(client_id=os.environ["FOID_CLIENT_ID"],
            private_key_pem=open("foid_private_key.pem").read(),
            key_id="a1b2c3d4")   # the "kid" from the public JWK (optional)
```

:::

The SDK signs a 60-second ES256 assertion (`iss` = `sub` = client ID, `aud` = the token URL, a random `jti`). FOID accepts EC P-256 (ES256) and RSA ≥ 2048-bit (RS256) public keys, and refuses assertions that expire more than 5 minutes ahead. Never paste the private key into the console: FOID rejects a JWK that contains private parts.

## What the person goes through

**Returning FOID users** sign in with email and code, then approve. In **live** mode:

- The **first time** they share with your business, FOID asks for a fresh **face re-match**: a short liveness check matched against their enrolled FOID face. Reusing an old check would let someone who can read the person's email share their identity. Later sign-ins to your business don't need it.
- If their FOID is missing something your scopes need, they finish just that step first: liveness enrolment, or NIN verification when you ask for `identity`.

**People without a FOID account** can still finish. Inside the popup they enter their name as on their NIN, then complete a hosted verification (NIN, plus liveness in live mode or when you ask for `liveness`). Your server gets the result either way, passed or failed. If their NIN check passed, FOID then offers **Save to FOID**: an explicit button, never pre-ticked, that creates a FOID account from what they just verified so they never repeat it. Saying no still gives you the result. `foid_account` tells you which happened.

The popup never redirects errors in your app's setup back to you. An unknown client ID, an origin or redirect URI that isn't registered, or a scope your app isn't allowed are shown to the person in the popup. Your page only sees `popup_closed` when they close it.

## Errors

**In the browser** (`onError` / `FoidSignInError.code`):

| Code | Meaning |
|---|---|
| `popup_closed` | The person closed the FOID window, or closed it after an error was shown there. |
| `access_denied` | The person pressed Cancel, or declined consent. |
| `popup_blocked` | The browser blocked the popup and you didn't pass `redirectUri`. |
| `state_mismatch` | The response didn't match this sign-in. It was ignored (protects against login CSRF). |
| `missing_client_id` | `<FoidProvider>` has no `clientId`. |

**From the token endpoint** (OAuth format: `{"error": "…", "error_description": "…"}`):

| HTTP | `error` | Meaning |
|---|---|---|
| 400 | `invalid_grant` | Code unknown, expired (60 s), already used, for another app, wrong `code_verifier`, or `redirect_uri` doesn't match |
| 400 | `unsupported_grant_type` | `grant_type` isn't `authorization_code` |
| 401 | `invalid_client` | Wrong client ID or secret, revoked secret, or a bad / expired / wrongly addressed client assertion |

The SDKs raise these as `FoidError` with `code` set to the `error` value.

## Security rules

- Only the **client ID** goes in the browser or mobile app. The client secret, private key and API key stay on your server.
- Exchange each code **once**, on your server, within 60 seconds.
- Pass a `nonce` and compare it with `result.nonce` if you need to bind the result to a session.
- Don't trust anything the browser tells you about the person. Use the exchange result.
- Register exact `https://` origins and redirect URIs for live apps.

Every token exchange appears in the console under **Request logs**, and each share appears in the person's **Connected apps** as "Continue with FOID", where they can revoke it.
