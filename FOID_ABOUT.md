# About FOID — Fintech Open Identity

**Hackaholics 7.0 | Wema Bank | Open Banking Track**

A reusable, self-updating financial identity layer. Verify once, stay current automatically, share only what's needed, everywhere you go.

---

## The Problem

Every time someone opens a new financial account or applies for a loan in Nigeria, they repeat the same KYC ritual from scratch — BVN, NIN, liveness check, manual review — even if they were already fully verified somewhere else last week. And once verified, that status is frozen: nobody re-checks whether the person is still a good risk until they've already defaulted.

## What FOID Does

FOID gives a person **one verified persona** made of two layers:

1. **Identity layer** — built once, via NIMC/BVN/NIN verification and a liveness check. Answers "who is this person."
2. **Financial trust layer** — built from Open Banking transaction data (via Okra/Mono sandbox), and critically, **it doesn't stop updating after issuance.** It keeps watching the connected account and automatically changes the credential's state when real financial behavior changes — a repayment bounces, income becomes unstable — with no human review required. Answers "can this person currently be trusted."

The user controls what gets shared, with whom, via a consent screen every time. Nothing is shared by default.

## Why This, Why Now

- **NIMC Act 2026** (signed July 1, 2026) makes NIMC Nigeria's Root Certification Authority for national identity. FOID does **not** compete with this — it consumes NIMC's identity infrastructure and builds the financial-trust layer on top, which NIMC does not provide.
- **CBN's 2026 KYC rules** raise the cost of onboarding for every institution (liveness checks, real-time BVN/NIN validation) — making reusable, once-verified credentials genuinely valuable, not just convenient.
- **Wema was part of the first live transaction on Nigeria's new National Payment Stack** (Nov 2025) — this project is built to sit naturally on that same real-time infrastructure direction.

## What Makes This Different From Existing Players

| They exist and do this | FOID does this instead |
|---|---|
| Smile ID, VerifyMe, YouVerify: one-off KYC check per app, every time | Verify once, reuse across every Wema product |
| CreditChek, Indicina: compute a credit score at a point in time, when asked | Never computes a score or lending recommendation — issues a **living credential** that updates its own state continuously; the lending decision always stays with the relying party |

**This boundary is deliberate and permanent, not just an MVP scope cut:** FOID does not do credit scoring, affordability scoring, or loan recommendations. If a feature starts looking like that, it doesn't belong in this repo — see `/docs/FOID_PRD.md` §8 for the full reasoning.

## Core Flow

1. **Persona creation** — liveness check + BVN/NIN validation + connect bank account via Open Banking sandbox
2. **Credential issuance** — signed claims issued: `identity_verified`, `bvn_validated`, `age_over_18`, `income_band`, `repayment_reliability`
3. **Selective disclosure** — user applies to a product; consent screen shows exactly which claims are requested; user approves/declines
4. **Continuous monitoring** — with ongoing consent, the system watches the live transaction feed for defined triggers and auto-updates credential state; the user is notified of any change and why

## Tech Stack (current)

- **Open Banking data:** Okra or Mono sandbox (Nigerian, CBN-licensed aggregators) — read-only, non-custodial
- **Identity verification:** simulated for the hackathon demo (real deployment would run through NIMC/a licensed KYC provider) — see FAQ Q36 for what's real vs. simulated
- **Credential format:** signed claims, conceptually aligned with W3C Verifiable Credentials / OIDC4VP patterns (JWT-based for MVP simplicity)
- **State-change triggers:** rule-based and deterministic for the demo — not ML — for reliability and auditability

*(Update this section as the actual stack gets decided — this reflects the plan, not a locked-in implementation yet.)*

## What FOID Is Not

- Not a wallet, not a bank — never holds or moves user funds
- Not a competing national identity authority — consumes NIMC's infrastructure, doesn't replace it
- Not a credit scoring or underwriting engine — issues claims, never makes the lending decision
- Not a bookkeeping/analytics dashboard — this idea was deliberately cut; see PRD for why
## Docs

- `/docs/FOID_PRD.md` — full product requirements, positioning, and design boundaries
- `/docs/FOID_FAQ.md` — 45+ Q&A covering technical, business, legal, and judge/investor questions — read this before pitching, especially the cheat sheet at the bottom


## Team Notes

- This repo is for **Hackaholics 7.0**, submitted for the **Open Banking** problem statement
- Non-custodial, non-lending, non-identity-authority — if you're building a feature and it starts crossing one of those lines, flag it before merging, not after
- Questions on positioning or scope should be checked against the PRD/FAQ first — most "should we add X" questions have already been stress-tested there
