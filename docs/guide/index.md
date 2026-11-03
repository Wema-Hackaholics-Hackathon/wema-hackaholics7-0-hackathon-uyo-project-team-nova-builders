# Introduction

FOID (Fintech Open Identity) lets your business verify customers without making them prove who they are again. A person verifies once with FOID (NIN, BVN, and a live face check), and then shares that result with each business they choose. FOID records the consent, and the person can take it back at any time from their FOID app.

For your business, that means:

- **Less onboarding friction.** People who already have a FOID share a verified identity in one tap.
- **Consent you can show.** Every read of a person's data goes through a consent grant with a purpose and scopes. Revoke it and the data stops.
- **No raw numbers to protect.** FOID never sends you a full NIN or BVN. You get "verified" plus the last 4 digits.

## Three ways to integrate

| | What it's for | Who collects consent | Face check | Start here |
|---|---|---|---|---|
| **Continue with FOID** | A sign-in / sign-up button. The person approves on FOID's screen and your server gets their verified details. | FOID, on its consent screen | A quick face re-match the first time they share with you (live) | [Continue with FOID](./continue-with-foid) |
| **Hosted verification** | Onboarding anyone, FOID account or not. You create a verification; the person completes NIN / BVN / liveness on a FOID page. | FOID, on the hosted page | Yes, a liveness check | [Hosted verification](./hosted-verification) |
| **Server-to-server checks** | Back-office checks when you already hold the number and the person's consent. | You — you attest you collected it | No | [NIN and BVN checks](./checks) |

How to choose:

- Your customers may already have a FOID, and you want sign-up to be one tap: **Continue with FOID**. People without a FOID can still finish inside the same popup.
- You need a liveness check, or you don't want to handle camera code or consent screens yourself: **Hosted verification**.
- You already have the NIN or BVN and consent from your own forms, and only need a match result: **Server-to-server checks**.

You can use more than one. Everything about a person lands on the same [subject](./concepts#subjects), keyed by your own `customer_ref`.

## What you need

- A **FOID console** account. Sign up at the console, verify your email, and you get an organisation with **test mode** ready to use.
- A **test API key** for the Open API (checks, verifications, subjects).
- For Continue with FOID, a **sign-in app** (client ID plus client secret or key pair).
- Optionally, a **webhook endpoint** so FOID can tell you when things finish.

Test mode is free and returns sandbox data, so you can build the whole flow before you go live. See [Test and live mode](./test-and-live).

## How these docs are organised

- **Start here:** [Quickstart](./quickstart) (your first API call in five minutes), [Core concepts](./concepts) and [Test and live mode](./test-and-live).
- **Integrate:** one guide per integration, plus [Subjects and consent](./subjects) and [Webhooks](./webhooks).
- **Production:** [Going live](./going-live), the [Security checklist](./security) and [Errors, limits, idempotency](./errors).
- **[SDKs](/sdks/):** Python, Node and React, plus the [Harbor example app](/sdks/example-app) that uses all three.
- **[API reference](/api/):** every endpoint with real example responses.
- **[Playground](/playground):** click the real "Continue with FOID" button and see what your server would receive.
