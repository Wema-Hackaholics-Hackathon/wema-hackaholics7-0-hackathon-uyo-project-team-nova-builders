# @foid/node — FOID Node SDK

Server-side SDK for FOID: the **Continue with FOID** code exchange (client secret or key pair), the **Open API** (checks, hosted verifications, subjects) and **webhook signature** verification.

- Node ≥ 18, ESM, **zero dependencies** (`fetch` + `node:crypto`), TypeScript types included.
- Holds your secrets: use it only on your server, never in a browser bundle.

## Install

Not on npm yet. Install from the FOID repository:

```bash
npm install ./sdks/node
```

## Quick start

```js
import { Foid, FoidError } from '@foid/node'

const foid = new Foid({
  apiKey: process.env.FOID_API_KEY,               // Open API: FOID_TEST_… / FOID_LIVE_…
  clientId: process.env.FOID_CLIENT_ID,           // Continue with FOID: foid_app_…
  clientSecret: process.env.FOID_CLIENT_SECRET,   // foid_cs_…
  // baseUrl: 'http://localhost:8000',            // when running FOID yourself
})
```

### Continue with FOID

Your front end (e.g. `@foid/react`) sends you `code` and `codeVerifier`. Exchange them once, within 60 seconds:

```js
app.post('/auth/foid', async (req, res) => {
  const person = await foid.oauth.exchange(req.body.code, req.body.codeVerifier)
  // person.subject_id: stable ID for this person at your business
  res.json({ name: `${person.subject.first_name} ${person.subject.last_name}` })
})
```

### Open API

```js
const result = await foid.checkNin({
  number: '12345678901', first_name: 'Ada', last_name: 'Obi',
  consent: { obtained: true, purpose: 'Account opening' },
})

const v = await foid.createVerification({
  checks: ['nin', 'liveness'], purpose: 'Open a wallet', customer_ref: 'cust_1001',
  return_url: 'https://acme.example/kyc/done', idempotencyKey: 'onboard-cust_1001',
})
console.log(v.hosted_url)   // send the person here

await foid.getVerification(v.id)
await foid.getSubject(result.subject_id)
await foid.request('DELETE', `/subjects/${result.subject_id}`)   // any endpoint
```

### Webhooks

```js
import express from 'express'
import { verifyWebhook } from '@foid/node'

app.post('/webhooks/foid', express.raw({ type: 'application/json' }), (req, res) => {
  const event = verifyWebhook(req.body, req.get('FOID-Signature'), process.env.FOID_WEBHOOK_SECRET)  // throws if invalid
  res.json({ received: true })
})
```

### Key pair instead of a client secret

```bash
npx foid keygen    # writes foid_private_key.pem, prints the public JWK for the console
```

```js
import { readFileSync } from 'node:fs'
const foid = new Foid({ clientId: 'foid_app_live_…', privateKeyPem: readFileSync('foid_private_key.pem', 'utf8') })
```

## API

| | |
|---|---|
| `new Foid({ apiKey, clientId, clientSecret, privateKeyPem, keyId, baseUrl, fetch })` | Client |
| `foid.oauth.exchange(code, codeVerifier, { redirectUri }?)` | Continue with FOID code → result |
| `foid.request(method, path, { json, params, idempotencyKey }?)` | Any Open API call (path relative to `/api/open/v1`) |
| `foid.getSubject(id)`, `createVerification({ idempotencyKey, ...body })`, `getVerification(id)`, `checkNin(body)`, `checkBvn(body)` | Helpers |
| `foid.webhooks.verify(...)` / `verifyWebhook(payload, header, secret, toleranceSeconds = 300)` | Webhook signature check → event |
| `createPkce()` | `{ codeVerifier, codeChallenge, state, nonce }` for server-led sign-in |
| `generateKeyPair()`, `clientAssertion(...)` | Key pairs |
| `FoidError` (`status`, `code`, `description`, `body`) | Errors |

## Security

- Keep the API key, client secret and private key on your server, in environment variables or a secret manager.
- Exchange each code once. A second exchange revokes the grant.
- Verify webhooks against the raw body.

## Docs

Full reference: the FOID docs site, page **SDKs → Node** (`docs/sdks/node.md`; run `cd docs && pnpm dev` for http://localhost:5177/sdks/node). Guides: Continue with FOID, Hosted verification, Webhooks. Working example: `demo/` (Harbor).
