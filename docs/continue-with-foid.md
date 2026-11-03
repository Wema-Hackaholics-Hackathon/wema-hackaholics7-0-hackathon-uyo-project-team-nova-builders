# "Continue with FOID" — design notes (discussion, 2026-11-02)

Status: **built (2026-11-03)** — phases 1–6 below. Captures what we agreed in conversation so it isn't lost.

## The three ways a business integrates

| | What it's for | Who proves what | Consent | Liveness | Status |
|---|---|---|---|---|---|
| **1. Server-to-server checks** (`/api/open/v1/checks/*`) | Back-office: "check this NIN/BVN/document" | API key proves the *business* | The business *attests* it got consent (weakest) | No (no camera) | Built |
| **2. Hosted flow / embed** (`/verifications` → FOID page or `foid-verify.js`) | Onboarding a customer, FOID account or not | API key proves the business | **FOID collects it** on its own page | Yes | Built |
| **3. "Continue with FOID"** (OAuth 2.0 / OpenID Connect) | People already verified on FOID share it | API key / client proves the business; **the person signs in and approves** | Person approves scopes on FOID's screen; revocable in Connected apps | Quick face re-match | Not built |

OAuth does **not** replace API keys: keys prove who the business is; OAuth proves the person agreed.

## Agreed flow — one flow that adapts to the person

1. **One input: email + one-time code** (decided: email — free, works today; phone/SMS later). No password.
   Existing FOID account → signed in. No account → continue as a new person.
2. **Consent screen:** "Sterling MFB wants: verified name, NIN status, BVN status, liveness. Allow?"
3. **Only what's missing** — each business declares what it needs:
   - returning, fully verified → nothing, or a 5-second face re-match (re-verify already exists);
   - returning, missing something (e.g. BVN) → just that step;
   - new person → NIN, BVN, document (OCR pre-fill), liveness.
4. **New people only — one tap: "Save this to FOID so you never repeat it."**
   Creates the account with the phone/email already confirmed in step 1 (no password; can set one later).
   Saying no still gives the business its result.

Not "sign up first, then verify": too much typing before the bank's checks, wrong moment, and NDPA —
data collected for a bank can't silently become a FOID account; account creation needs its own clear yes.

## What FOID shares: proof, not numbers ("confirm, don't reveal")

- Businesses get **attestations**: "NIN verified against NIMC on 2 Nov, last 4 8901, name + DOB match, liveness
  passed today, credential active" — never the full NIN/BVN from our database.
- When a bank must keep the full number (CBN KYC), **the person types it**; FOID compares it with the stored
  keyed hash and confirms "that's the NIN we verified". No reveal, no paid lookup, works for everyone.
- Storage today: FOID users — NIN and BVN encrypted + hash + last 4; business-verified people — hash + last 4 only.
- Optional later: an explicit, per-bank "release my NIN" consent for FOID account holders. Off by default.

## To build

- Console: **Apps** page — register an app per business per env: client id/secret, exact redirect URIs, allowed scopes.
- User app: FOID sign-in (code-based) + consent screen + "Save to FOID".
- Backend: OAuth/OIDC endpoints (authorize with PKCE, token, userinfo/claims), scopes mapped to the existing
  consent scopes (identity, contact, liveness, financial); "what's missing" step-up logic; confirm-NIN/BVN endpoint;
  revocation kills tokens (consent revocation already stops data + webhooks).
- Hosted flow gets an "Already have FOID? Share it instead" button using the same consent.

## SDK order (proposed)

1. Server SDKs: Node + Python (keys, idempotency, webhook signature check), PHP later.
2. Web: `foid-verify.js` as an npm package + React component.
3. Mobile: React Native + Flutter wrappers (hosted flow with camera), native later.
4. "Continue with FOID": standard OAuth libraries work — ship a branded button + guide.

## Decisions (2026-11-03)

1. **In scope** — we're building it.
2. **Email** one-time code (not SMS/WhatsApp).
3. **"Save to FOID" is an explicit button**, never pre-ticked (NDPA: account creation needs its own clear yes).
4. **Fresh face re-match for every new business.** The first time a person shares with a business, they do a
   ~5-second liveness check that is matched against their enrolled FOID face. The business gets "liveness passed
   today, same person as the verified identity". Reusing an old check would let someone who knows the email
   (and can read the code) share another person's identity. Returning to a business they already approved needs no
   re-match unless the business asks for one (e.g. high-value actions).
5. **Attested-consent checks (way 1) allowed in Live as well as the hosted flow.** Guardrails: Live only after KYB
   approval; every grant is labelled `business_attested` vs `hosted_flow` (already stored as `source`), shown to the
   person in Connected apps and in the business's own logs, so the weaker kind is always visible.
6. **SDKs: Python + Node (server) and a React component** in the style of `@react-oauth/google`:
   `<FoidProvider clientId>` + `<ContinueWithFoid onSuccess={({ code }) => …} />` (FOID-branded button, popup
   window, `postMessage` back, redirect fallback when popups are blocked) and a `useFoidLogin()` hook.

## Keys: what lives where (decided 2026-11-03: separate client secret, not the API key)

Three credentials, each able to do as little as possible:

| | Where it lives | What it can do |
|---|---|---|
| **Client id** `foid_app_…` (public) | Browser / React component / mobile app | Only opens the popup. Reads nothing. |
| **Client secret** `foid_cs_test_…` / `foid_cs_live_…` | Business's server, per app, shown once, stored hashed | Only exchanges a one-time code for what the person just approved, for that one app. |
| **API key** `FOID_TEST_…` / `FOID_LIVE_…` | Business's server | Everything else: checks, hosted verifications, reading a subject later, deleting, webhooks. |

Why not reuse the API key as the client secret: an OAuth secret ends up in more places (auth libraries,
NextAuth/Passport config, "quick test" mobile builds). If it's the API key, one leak exposes every customer the
business has ever verified and runs paid checks on its bill. A separate secret limits a leak to "exchange codes
for this app" — and those codes are useless without the steps below.

Protections on every code exchange (OAuth 2.1 / security BCP):
- **PKCE required** for every app, web and mobile — a stolen code can't be exchanged without the verifier that
  never left the person's browser.
- Code: **single use, 60 seconds**, bound to client id + exact redirect URI + PKCE verifier. A second attempt to use a
  code revokes everything issued from it.
- **`state` + `nonce`** checked by the SDK (stops login CSRF / replayed sign-ins); popup results only accepted via
  `postMessage` from the FOID origin to a registered origin.
- Client secret: hashed (like API keys), rotate with an overlap window (old one works 24 h), IP allow-list applies
  in Live, email alert on create/rotate, every exchange in Request logs.
- **Live option for banks — key pair instead of a secret (`private_key_jwt`)**: the business's server keeps a private
  key and signs each exchange; FOID stores only the public key, so nothing secret exists on FOID's side to leak.
  The SDKs generate the pair; the console takes the public key.
- What an exchange returns: the person's result + `subject_id`. Reading that person again later uses the API key
  and still goes through consent (revoked → 403), so the secret never becomes a standing data key.

Flow: React button (client id) → popup → `code` to the business's backend → `foid.oauth.exchange(code)` (Node /
Python SDK, client secret + PKCE verifier) → result. Identity data never goes straight to the browser.

## Test mode (sandbox)

- **Everything in test mode passes and returns dummy data** (checks, hosted flow, webhooks), so developers learn
  the response structure without touching real identities.
- **Except "Continue with FOID" sign-in, which is real — like Google sign-in:** any FOID user can sign in to a test
  app to see how login works. The consent screen is clearly marked **"Test app — not checked by FOID"**.
  The business gets the person's **real first and last name only**; everything else (NIN/BVN status, last 4, date
  of birth, liveness, credential state) is dummy data in the live shape. No face re-match in test mode.
- **localhost:** test apps accept any `http://localhost:<port>` / `http://127.0.0.1:<port>` origin and redirect
  without registering it (loopback rule, RFC 8252), plus registered https URLs.
- **Live apps:** https only, exact registered origins and redirect URIs; localhost refused; real data; face re-match.
- Test and live data stay separate, as everywhere else.

## Build plan — all phases done

1. **Apps (console + backend)** — register a "Continue with FOID" app per business per env: name, allowed
   origins, exact redirect URIs, allowed scopes, client id, client secrets (shown once, hashed, rotate with a 24 h
   overlap, revoke), optional public key for `private_key_jwt` (Live). Test apps also accept localhost.
2. **OAuth core (backend)** — `/oauth/authorize` request validation (client, origin/redirect, PKCE S256, state,
   nonce, scopes), one-time codes (60 s, single use, replay → revoke), token exchange on the Open API with client
   secret or `private_key_jwt`, result payload (`subject_id`, attestations), consent grants with
   `source="foid_oauth"`, test-mode dummy data except the real name.
3. **Sign-in popup (user app)** — email one-time code, consent screen ("Test app — not checked by FOID" in test),
   only-missing steps, fresh face re-match per new business (Live), explicit "Save to FOID" for new people,
   `postMessage` back to the opener / redirect fallback.
4. **Server SDKs** — Python + Node: PKCE helpers, `exchange(code)`, `private_key_jwt` signing, webhook signature
   check, API-key client.
5. **React component** — `<FoidProvider clientId>`, `<ContinueWithFoid onSuccess>`, `useFoidLogin()`.
6. **Hosted flow + docs** — "Already have FOID? Share it instead" button; developer guide.

## Developer guide

**1. Register an app** — FOID Console → Sign-in apps → Create app. Add your site's origin (where the button
runs) and, for the no-popup fallback, a redirect URI. Copy the **client ID** (public) and the **client
secret** (shown once). Test apps accept `http://localhost:<any port>` without registering it.

**2. Frontend — the button** (`sdks/react`, `@foid/react`)

```jsx
import { FoidProvider, ContinueWithFoid } from '@foid/react'

<FoidProvider clientId="foid_app_test_…" foidUrl="https://app.foid.ng">
  <ContinueWithFoid
    scope="identity contact"                       // profile (name) is always included
    onSuccess={({ code, codeVerifier }) => fetch('/auth/foid', { method: 'POST', body: JSON.stringify({ code, codeVerifier }) })}
    onError={(e) => console.log(e.code)}           // access_denied | popup_closed | popup_blocked | state_mismatch
  />
</FoidProvider>
```

Custom button: `const login = useFoidLogin({ scope, onSuccess, onError })` → `<button onClick={login}>`.
No React: `import { signInWithFoid } from '@foid/react/core'`. Popup blocked → pass `redirectUri` and call
`handleRedirectCallback()` on that page.

**3. Backend — exchange the code** (within 60 s, once)

```js
import { Foid } from '@foid/node'
const foid = new Foid({ clientId, clientSecret, baseUrl: 'https://api.foid.ng' })
const person = await foid.oauth.exchange(code, codeVerifier)
```
```python
from foid import Foid
foid = Foid(client_id=..., client_secret=..., base_url="https://api.foid.ng")
person = foid.oauth.exchange(code, code_verifier)
```

Raw HTTP: `POST /api/open/v1/oauth/token` with `grant_type=authorization_code`, `code`, `code_verifier`
(and `redirect_uri` in redirect mode), authenticated with HTTP Basic `client_id:client_secret` or a
`private_key_jwt` assertion. Errors use OAuth's format: `{"error": "invalid_grant", "error_description": …}`.

**The result** (`object: "foid_sign_in"`): `subject_id` (use it with your API key later — consent still applies),
`subject` (name; with `identity`: date of birth, `nin`/`bvn` `{verified, last4}`; with `contact`: email, masked
phone; with `liveness`: `passed_at`), `checks`, `foid_account`, `face_rematched_at`, `nonce`, `sandbox`.
In test mode only the name is real.

**Key pair instead of a secret** (recommended for banks): `npx @foid/node keygen` or `python -m foid keygen`,
paste the public JWK in Console → Sign-in apps → Edit → Key pair, then pass `privateKeyPem` /
`private_key_pem` instead of the client secret.
