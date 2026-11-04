# Node SDK — `@foid/node`

A server-side SDK for Node ≥ 18. It covers the Continue with FOID code exchange (client secret or key pair), the Open API, webhook signature verification and PKCE helpers. It's ESM, has **no dependencies** (it uses `fetch` and `node:crypto`), and ships TypeScript types. It holds secrets, so **never bundle it into a browser app**.

```bash
npm install ./sdks/node   # see SDKs → Install; not on npm yet
```

## Quick start

```js
import { Foid, FoidError } from '@foid/node'

const foid = new Foid({
  apiKey: process.env.FOID_API_KEY,             // Open API
  clientId: process.env.FOID_CLIENT_ID,         // Continue with FOID
  clientSecret: process.env.FOID_CLIENT_SECRET,
})

// Continue with FOID: the code + verifier from your front end
const person = await foid.oauth.exchange(code, codeVerifier)
console.log(person.subject_id, person.subject.first_name)

// Open API
const result = await foid.checkNin({
  number: '12345678901', first_name: 'Ada', last_name: 'Obi',
  consent: { obtained: true, purpose: 'Account opening' },
})
```

## `new Foid(options)`

| Option | Used for |
|---|---|
| `apiKey` | The Open API (`request()` and the helpers). `FOID_TEST_…` / `FOID_LIVE_…`. |
| `clientId` | `oauth.exchange()`: your sign-in app's client ID. |
| `clientSecret` | `oauth.exchange()` for client-secret apps. |
| `privateKeyPem` | `oauth.exchange()` for key-pair apps. If set, it's used instead of `clientSecret`. |
| `keyId` | Optional `kid` put in the assertion header. |
| `baseUrl` | The FOID API host. Default `https://foid-iy7u.onrender.com`; e.g. `http://localhost:8000` locally. |
| `fetch` | A custom `fetch` implementation (for tests, proxies or retries). Default `globalThis.fetch`. |

All options are optional. Pass only the credentials you use.

### `foid.oauth.exchange(code, codeVerifier, { redirectUri }?)`

Exchanges the one-time code from the sign-in popup for the person's result. Calls `POST /api/open/v1/oauth/token`. Do it **once, within 60 seconds**.

- With `clientSecret`: sends HTTP Basic `clientId:clientSecret`.
- With `privateKeyPem`: sends a signed `client_assertion` (ES256, valid 60 seconds, `aud` = the token URL).
- `redirectUri` is required only in redirect mode, and must be the exact URI used to start sign-in.

Resolves to the result (`FoidSignInResult` in the types). See [the result](/guide/continue-with-foid#the-result).

Rejects with:

- `Error('clientId is required')`, or `Error('Pass clientSecret, or privateKeyPem for a key-pair app')`.
- `FoidError` from the token endpoint, with `code` set to the OAuth error: `invalid_grant` or `invalid_client`.

```js
try {
  const person = await foid.oauth.exchange(code, codeVerifier)
} catch (e) {
  if (e instanceof FoidError && e.code === 'invalid_grant') {
    // ask the person to sign in again
  }
}
```

### `foid.request(method, path, { json, params, idempotencyKey }?)`

Calls any Open API endpoint with your API key. `path` is relative to `/api/open/v1`.

- `json`: the request body. `params`: query parameters (an object). `idempotencyKey`: sent as `Idempotency-Key`.
- Resolves to the parsed JSON, or `null` for `204` (e.g. `DELETE`).
- Rejects with `Error('apiKey is required for the Open API')` without an API key, and `FoidError` for any `4xx` / `5xx`.

```js
await foid.request('GET', '/verifications', { params: { status: 'pending' } })
await foid.request('POST', `/verifications/${vid}/cancel`)
await foid.request('GET', `/subjects/${sid}/trust-report`)
await foid.request('DELETE', `/subjects/${sid}`)                        // null
await foid.request('POST', '/checks/nin', { json: body, idempotencyKey: 'chk-cust_1001' })
```

### Open API helpers

| Method | Calls |
|---|---|
| `getSubject(id)` | `GET /subjects/{id}` |
| `createVerification({ idempotencyKey, ...body })` | `POST /verifications`. `idempotencyKey` becomes the header; the rest is the body. |
| `getVerification(id)` | `GET /verifications/{id}` |
| `checkNin(body)` | `POST /checks/nin` |
| `checkBvn(body)` | `POST /checks/bvn` |

Request bodies use the API's snake_case field names (`customer_ref`, `first_name`, `return_url`, …).

```js
const v = await foid.createVerification({
  checks: ['nin', 'liveness'], purpose: 'Open a wallet',
  customer_ref: 'cust_1001', first_name: 'Ada', last_name: 'Obi',
  return_url: 'https://acme.example/kyc/done',
  idempotencyKey: 'onboard-cust_1001',
})
console.log(v.hosted_url)
```

### `foid.webhooks.verify(payload, header, secret, toleranceSeconds?)`

The same as [`verifyWebhook`](#verifywebhook).

## `verifyWebhook(payload, header, secret, toleranceSeconds = 300)` {#verifywebhook}

```js
import { verifyWebhook } from '@foid/node'
const event = verifyWebhook(rawBody, req.headers['foid-signature'], process.env.FOID_WEBHOOK_SECRET)
```

Checks the `FOID-Signature` header against the **raw** body (`Buffer` or string) and returns the parsed event. Throws an `Error` if the header is missing or malformed, the timestamp is outside the tolerance, or the signature doesn't match. With Express, read the body with `express.raw({ type: 'application/json' })`. See [Webhooks](/guide/webhooks#verify-the-signature).

## `createPkce()`

```js
import { createPkce } from '@foid/node'
const { codeVerifier, codeChallenge, state, nonce } = createPkce()
```

For servers that start the sign-in themselves. Keep `codeVerifier`, `state` and `nonce` server-side. See [Server-led sign-in](/guide/continue-with-foid#server-led-sign-in).

## Key pairs

| Function | Returns |
|---|---|
| `generateKeyPair()` | `{ privateKeyPem, publicJwk }`: a new EC P-256 key (PKCS#8 PEM; JWK with `alg: "ES256"` and a random `kid`). |
| `clientAssertion(privateKeyPem, clientId, audience, kid?)` | The signed ES256 JWT that `oauth.exchange` sends. You rarely need it directly. |

From the command line (the package's `foid` binary):

```bash
npx foid keygen
```

This writes `foid_private_key.pem` (mode `600`, refusing to overwrite an existing one) and prints the public JWK to paste into **Sign-in apps → Edit → Key pair**. Then:

```js
import { readFileSync } from 'node:fs'
const foid = new Foid({ clientId: 'foid_app_live_…', privateKeyPem: readFileSync('foid_private_key.pem', 'utf8'), keyId: '<kid>' })
```

## Errors

### `FoidError`

Thrown for any non-2xx response. `err.message` is `"<status> <code>: <description>"`.

| Property | |
|---|---|
| `status` | HTTP status |
| `code` | The Open API `error.code` (e.g. `consent_revoked`), the OAuth `error` for the token endpoint (e.g. `invalid_grant`), or `http_error` when the body has neither (e.g. `422` validation errors, `429`) |
| `description` | Human-readable message |
| `body` | The parsed response body |

```js
try {
  await foid.getSubject(sid)
} catch (e) {
  if (e instanceof FoidError && e.code === 'consent_revoked') {
    // stop using and delete this person's data
  }
}
```

Network failures reject with `fetch`'s own `TypeError`. Missing credentials reject with a plain `Error`.

## Exports

| Name | Kind |
|---|---|
| `Foid` (also the default export) | client class |
| `FoidError` | error class |
| `createPkce`, `generateKeyPair`, `clientAssertion`, `verifyWebhook` | functions |
| `DEFAULT_BASE_URL` | `"https://foid-iy7u.onrender.com"` |

Types (`FoidOptions`, `FoidSignInResult`, …) are in `index.d.ts`.
