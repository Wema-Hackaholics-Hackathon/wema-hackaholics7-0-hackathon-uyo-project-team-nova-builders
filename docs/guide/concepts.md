# Core concepts

## Organisations and environments

Your business is an **organisation** in the FOID console. Every organisation has two separate environments:

- **Test:** sandbox data, free, available immediately.
- **Live:** real lookups, billed, available after FOID approves your business (KYB).

Test and live never mix. Keys, sign-in apps, webhooks, subjects and logs all belong to one environment. A test key can't read a live subject. See [Test and live mode](./test-and-live).

## Subjects

A **subject** is a person as your business knows them. Every check, verification and Continue with FOID sign-in is recorded against a subject, and the subject's `id` (`subject_id`) is stable for your business.

- Subjects belong to **one** organisation and environment. Two businesses that verify the same person each get their own subject and never see each other's.
- A person doesn't need a FOID account to be a subject. `has_foid_account` tells you whether the subject is linked to one.
- FOID never stores a subject's full NIN or BVN: only a keyed hash (to recognise the same number again) and the last 4 digits.

### customer_ref

`customer_ref` is **your** ID for the person, such as your user ID. Pass it on checks and verifications and FOID reuses the same subject for that reference, so a person's NIN check, BVN check and liveness all end up together. You can also pass `subject_id` directly.

## Consent and scopes

Every read of a person's data goes through a **consent grant** between the subject and your organisation. A grant has a purpose and a set of **scopes**:

| Scope | What you can read |
|---|---|
| `profile` | Name: first, middle, last. Always included in Continue with FOID. |
| `identity` | NIN / BVN check results (verified + last 4), and the name and date of birth on record |
| `liveness` | Liveness results, and re-verification against the captured face |
| `contact` | Email address and phone number (phone masked) |
| `financial` | The trust report and `credential.state_changed` events. FOID account holders only. |

Checks imply scopes: `nin` and `bvn` need `identity`; `liveness` and `reverify` need `liveness`. On a hosted verification you can ask for `contact` and `financial` on top.

Where consent comes from is recorded as the grant's **source**:

| Source | How it was collected | Strength |
|---|---|---|
| `foid_oauth` | The person approved on FOID's consent screen in [Continue with FOID](./continue-with-foid) | Strongest: the person signed in and approved |
| `hosted_flow` | The person accepted FOID's consent screen in a [hosted verification](./hosted-verification) | Strong: FOID showed and recorded it |
| `business_attested` | You sent `consent.obtained: true` with a [server-to-server check](./checks) | Weakest: your own attestation |

The person sees the source in **Connected apps** in their FOID app. You see it in your own logs.

**Revocation.** A person can revoke your access at any time. From that moment, reads of their data return `403 consent_revoked`, verification results come back redacted, queued webhooks about them are cancelled, and you get one `consent.revoked` event. See [Subjects and consent](./subjects#when-a-person-revokes-consent).

## Credential state

A FOID account holder has a living **credential**, not a one-time check. Its state can change after verification, for example when connected bank data shows something that needs another look:

`active` → `under_review` → `downgraded` → `revoked`

Businesses with the `financial` scope can read the state in the [trust report](./subjects#trust-report) and get `credential.state_changed` webhooks when it changes. The credential state is a set of verified signals, not a score. The decision about what to do stays with you.

## Keys and credentials {#keys-and-credentials}

FOID gives you four kinds of credential. Each can do as little as possible, so a leak of one has limited damage.

| Credential | Looks like | Where it lives | What it can do |
|---|---|---|---|
| **API key** | `FOID_TEST_…` / `FOID_LIVE_…` | Your server only | The whole Open API: checks, verifications, subjects. Shown once, stored hashed. |
| **Client ID** | `foid_app_test_…` / `foid_app_live_…` | Browser and mobile apps (public) | Only opens the Continue with FOID popup for your sign-in app. Reads nothing. |
| **Client secret** | `foid_cs_test_…` / `foid_cs_live_…` | Your server only | Only exchanges a one-time sign-in code for that one app. Shown once, stored hashed. When you rotate it, the old secret keeps working for 24 hours. |
| **Key pair** (`private_key_jwt`) | A private key PEM + a public JWK | Private key on your server, public key in the console | Replaces the client secret: your server signs each code exchange. FOID only holds the public key, so FOID holds no secret to leak. |

Why the client secret isn't the API key: OAuth secrets tend to end up in more places, such as auth libraries and config files. If the API key were used as the secret, one leak would expose every customer you've ever verified. A separate secret limits a leak to "exchange codes for this app", and those codes are useless without the PKCE verifier.

The browser only ever sees the **client ID**. The API key, client secret and private key stay on your server.

## Test and live data

- Test mode returns **sandbox data**. Checks pass or fail by the [last digit](./test-and-live#sandbox-numbers), and Continue with FOID shares the person's real name but sandbox data for everything else.
- Live mode returns real results and is billed per check.

More in [Test and live mode](./test-and-live).
