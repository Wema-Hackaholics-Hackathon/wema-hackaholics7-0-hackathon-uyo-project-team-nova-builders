# "Continue with FOID" — design notes (discussion, 2026-11-02)

Status: **design only, nothing built yet.** Captures what we agreed in conversation so it isn't lost.

## The three ways a business integrates

| | What it's for | Who proves what | Consent | Liveness | Status |
|---|---|---|---|---|---|
| **1. Server-to-server checks** (`/api/open/v1/checks/*`) | Back-office: "check this NIN/BVN/document" | API key proves the *business* | The business *attests* it got consent (weakest) | No (no camera) | Built |
| **2. Hosted flow / embed** (`/verifications` → FOID page or `foid-verify.js`) | Onboarding a customer, FOID account or not | API key proves the business | **FOID collects it** on its own page | Yes | Built |
| **3. "Continue with FOID"** (OAuth 2.0 / OpenID Connect) | People already verified on FOID share it | API key / client proves the business; **the person signs in and approves** | Person approves scopes on FOID's screen; revocable in Connected apps | Quick face re-match | Not built |

OAuth does **not** replace API keys: keys prove who the business is; OAuth proves the person agreed.

## Agreed flow — one flow that adapts to the person

1. **One input: phone (or email) + one-time code.** No password.
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

## Open decisions

1. Is "Continue with FOID" in scope for the hackathon?
2. One-time code by phone (SMS/WhatsApp, costs per message) or email (free, works today)?
3. "Save to FOID": explicit button (recommended) vs pre-ticked box (weak consent under NDPA).
4. Fresh face re-match for every new business (recommended) or reuse a recent one?
5. Should attested-consent checks (way 1) be allowed in Live, or only the hosted flow?
6. Which SDK languages first?
