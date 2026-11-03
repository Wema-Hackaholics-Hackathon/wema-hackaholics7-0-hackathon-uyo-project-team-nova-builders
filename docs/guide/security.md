# Security checklist

Go through this before you go live, and again whenever you change how you handle FOID credentials.

## Credentials

- [ ] The **API key**, **client secret** and **private key** exist only on your servers, in a secret manager or environment variables. Never in front-end code, mobile apps, git or logs.
- [ ] The browser and mobile apps only ever see the **client ID** (and a verification's `client_token`, which works for that one verification only).
- [ ] Live sign-in apps use a **key pair** (`private_key_jwt`) where possible.
- [ ] You know how to rotate each credential, and who can. See [Going live](./going-live#_4-lock-it-down).
- [ ] An **IP allow-list** is set for live API keys.
- [ ] Your team uses two-step sign-in, and roles are as low as they can be.

## Continue with FOID

- [ ] Codes are exchanged on your **server**, **once**, within 60 seconds. A second exchange revokes the grant.
- [ ] You let the SDK check `state` (it does by default), and pass and compare a `nonce` if you bind sign-in to a session.
- [ ] You trust only the exchange result, never anything the browser reports about the person.
- [ ] Live origins and redirect URIs are exact `https://` URLs you control.
- [ ] You key your users on `subject_id`, not on email or name.

## Webhooks

- [ ] Every webhook is verified with the signing secret against the **raw** body, and rejected if older than 5 minutes.
- [ ] Your handler is idempotent (de-duplicates on `FOID-Event-Id`) and returns 2xx quickly.
- [ ] The endpoint is `https://` on a public address.

## Hosted verification

- [ ] You confirm the result on your server (`verification.completed` webhook or `GET /verifications/{id}`). Never act on `onComplete` or `return_url` alone.
- [ ] You send an `Idempotency-Key` when creating verifications.

## Personal data and consent

- [ ] For server-to-server checks, you really collected the person's consent before sending `consent.obtained: true`. It's your legal attestation.
- [ ] You ask for the fewest scopes you need.
- [ ] On `consent.revoked`, you stop using the person's data and delete what you hold, under your obligations (NDPA 2023).
- [ ] You use `DELETE /subjects/{id}` when a customer asks you to erase their data.
- [ ] You don't log full request or response bodies that contain personal data.

## Operations

- [ ] Errors are handled by `error.code`, with retries and backoff for `429` and `5xx`.
- [ ] You record `FOID-Request-Id` from responses, so you can trace a call in **Request logs** and with support.
