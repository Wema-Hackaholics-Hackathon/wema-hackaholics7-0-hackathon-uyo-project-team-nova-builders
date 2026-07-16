# FOID — Fintech Open Identity
### Product Requirements Document
**Hackaholics 7.0 — Open Banking Track | Wema Bank**

---

## 1. Problem Statement

Every time a Nigerian opens a new financial account, applies for a loan, or signs up for a fintech product, they repeat the same onboarding ritual: BVN, NIN, a selfie for liveness, sometimes a utility bill, followed by a manual review that can take hours to days. This happens identically at every single institution they touch — a rider who's already fully verified at one bank starts from zero at the next.

Two things make this worse than a UX annoyance:

- **High drop-off.** Onboarding friction is a proven conversion killer, especially for lower-income and informal-sector users who are exactly who financial inclusion is supposed to reach.
- **Shallow trust signals.** Identity verification alone (BVN + NIN + liveness) tells a lender *who someone is* — not *whether they're a good risk*. Institutions are left doing identity and creditworthiness as two disconnected problems.

FOID solves both by giving a person one verified, reusable **persona** — identity-verified once, financial-trust-scored continuously — that they carry with them, and control, across every financial relationship they enter.

---

## 2. Why Now

This idea only makes sense in mid-2026 Nigeria, for three concrete, dated reasons:

1. **NIMC Act 2026** (signed July 1, 2026) makes NIMC Nigeria's Root Certification Authority and national Public Key Infrastructure provider, with a "One Person, One Identity, One Number" mandate and a new General Multipurpose Card. This is the government building the *identity* half of this problem at national scale — which is why FOID does not attempt to compete with it (see §4, Positioning).
2. **CBN 2026 KYC rules** tighten requirements for liveness checks, real-time BVN/NIN validation, and device binding on all new digital onboarding — raising the cost of KYC for every institution, which raises the value of doing it once, well, and reusably.
3. **Wema's own National Payment Stack position** — Wema was party to the first live transaction on Nigeria's new real-time interbank settlement rail (Nov 2025) — signals Wema is positioned to lead on infrastructure plays like this, not just retail products.

---

## 3. What FOID Is (Plain Terms)

FOID is a **verified persona layer**, not a wallet and not a bank. A user completes identity verification once — liveness check, BVN validation, NIN validation, consuming NIMC's national identity infrastructure rather than duplicating it — and FOID adds a second layer on top that NIMC's card does not provide: a **financial trust signal**, derived from the user's own bank transaction history via Open Banking (Mono/Okra), covering things like income stability, account activity, and credit-relevant behavior.

The result is a single, cryptographically-verifiable, user-controlled credential set that answers two questions any lender or relying party needs:
- **Who is this person?** (identity — built on NIMC/BVN/NIN)
- **Can this person be trusted financially?** (behavior — built on Open Banking)

The user shares only the specific claims a given service needs (e.g. "age over 18," "income band," "BVN validated") via a consent screen — not raw documents, not raw bank statements.

---

## 4. Positioning — Why This Survives Scrutiny

This is the single most important section of this document, because the naive version of this idea is dead on arrival.

**FOID is explicitly NOT:**
- A competing national identity authority (that's now NIMC's legal mandate, enforced with criminal penalties under the NIMC Act 2026)
- A generic KYC-verification API (that's the existing, crowded lane occupied by Smile Identity, VerifyMe, IdentityPass, YouVerify — one-off verification calls per transaction)
- A generic credit-scoring API (CreditChek, CrediSure, Indicina already do open-banking-based credit intelligence for lenders)

**FOID IS:**
- A **relying-party-side product built for Wema**, that consumes NIMC's national identity infrastructure (rather than re-building it) and layers Wema-specific reusability on top
- The bridge between one-off KYC verification (what exists today) and true portable, user-controlled, cross-product reuse (what doesn't exist yet, inside a single bank's own ecosystem)
- Scoped initially to reuse **within Wema's own product suite** (ALAT personal accounts, SME accounts, lending, embedded partners) — not an attempt to become the "Login with Google" of Nigerian finance on day one. That ambition is a *possible future*, not the hackathon pitch.

This is the honest, defensible answer if a judge asks "why isn't this just NIMC's job" or "how is this different from CreditChek."

---

## 5. Where Open Banking Actually Gets Used — Living Credentials, Not a Score

This is deliberately the load-bearing part of the product, not a bolt-on — and it's the specific mechanism that keeps FOID out of CreditChek/Indicina's lane while still being genuinely powerful.

**The core design decision:** FOID does not compute a credit score or an affordability/underwriting recommendation. That decision stays with the lender. What FOID does instead is give every issued credential a **state**, not just a value — `active`, `under_review`, `downgraded`, `revoked` — and uses the Open Banking transaction feed to **automatically change that state** when real financial behavior changes, with zero human review and no separate dashboard.

| Persona Layer | Data Source | What It Proves | Mechanism |
|---|---|---|---|
| Identity | NIMC (NIN), BVN, liveness check | Who the person is | Verified once, static unless revoked for fraud |
| Financial Trust Signal | Open Banking API (Mono/Okra) — transaction history | Income stability, repayment reliability | **Continuously monitored, self-updating credential state** |

**Concrete trigger examples for the demo:**
- `financial.income_stability` auto-downgrades from `high` → `volatile` when the transaction feed shows a sharp, sustained drop or erratic pattern in expected inflows
- `financial.repayment_reliability` auto-flags when a recurring loan-repayment debit (detected the same way this idea's earlier debt-consolidation concept would) bounces or goes late
- A downgrade **propagates instantly** to every relying party checking that persona — a Wema lending product sees the updated state the moment it next checks, with no separate monitoring system of its own to build or maintain

**Why this is genuinely different from CreditChek/Indicina, precisely:** they compute a score *when asked*, at a single point in time. FOID's credential is a **living object that updates itself continuously from real behavior** — the trust signal is always current, never stale the moment after it's checked. That's a different technical shape, not a different UI on the same underlying idea. FOID never tells a lender *what to decide* — it tells them, continuously, *what's currently true*.

**Transparency requirement, not optional:** a state downgrade must never be a silent, black-box event. The affected user is notified — what changed, why, and what they can do — every time. Without this, the "living credential" mechanism looks like invisible surveillance rather than transparent, user-controlled infrastructure, which would undercut the consent-based positioning this whole product depends on.

**Why Wema pays for it, concretely:** this directly replaces the manual, human loan-monitoring role uncovered during this idea's research — MFBs and lenders currently track repayment trends by hand, periodically. FOID makes that continuous and automatic, and because it's baked into the shared persona rather than a per-product feature, every Wema product benefits from it at once instead of each team building its own monitoring pipeline.

---

## 6. Core User Flow

1. **Persona Creation (one-time):** User completes liveness check + BVN/NIN validation (via NIMC infrastructure) and connects their bank account via Open Banking (Mono/Okra, read-only, consented).
2. **Credential Issuance:** FOID issues signed, verifiable claims — identity claims (name, age, BVN/NIN validated) and financial claims (income band, account stability) — stored in the user's persona.
3. **Selective Disclosure:** When the user applies for a new Wema product (SME account, working capital loan, ALAT upgrade), they see a consent screen: "This product wants: BVN validated, income band. Share?" They approve or decline per request.
4. **Reuse:** Subsequent Wema products request only the incremental claims they need — no repeated document upload, no repeated liveness check, no repeated manual review for already-verified attributes.
5. **Continuous state updates:** With ongoing consent, FOID keeps watching the connected account for defined trigger events (income disruption, repayment bounce) and automatically updates the relevant credential's state — no re-verification request needed, no dashboard for a human to check. The user is notified of any state change and why.

---

## 7. Why Wema Benefits (Not Just the User)

- **Lower cost per onboarded customer** — fewer manual KYC reviews, less repeated document handling, once a persona is established.
- **Higher conversion** — friction is the single biggest driver of onboarding drop-off; removing repeat KYC steps for returning or cross-product users directly improves activation.
- **Better risk-based decisioning** — the financial trust signal (built from real Open Banking data, not self-reported income) lets Wema offer differentiated products (higher limits, faster approval) to genuinely lower-risk customers instead of applying blunt, uniform caution.
- **Cross-sell infrastructure** — a customer who onboards for a personal ALAT account becomes a near-instant approval for an SME account or loan product later, because the persona already exists.

---

## 8. Non-Goals for Hackathon MVP

To keep the build honest and demoable, explicitly out of scope for v1:

- Becoming a cross-bank, cross-institution identity network (that's a post-hackathon ambition, not a weekend build)
- Any custody of user funds (FOID never holds money — see §9)
- General bookkeeping/analytics dashboards, exports, or "AI accountant" features — deliberately cut from this pitch to avoid diluting the trust-infrastructure story with a saturated, unrelated product category
- **Computing credit scores, affordability scores, or recommended loan/installment amounts.** This is a deliberate, permanent boundary, not just an MVP scope cut — it's what keeps FOID out of CreditChek/Indicina's territory (see §5). FOID issues verified, self-updating claims about a person's financial behavior; the lending decision itself always stays with the relying party.

---

## 9. Licensing & Compliance Posture

FOID never becomes a licensed financial institution and never custodies funds or performs payment initiation in this version — it is a **read-only consumer of two already-licensed data sources**:
- **Identity data** via NIMC's national infrastructure (BVN/NIN validation)
- **Financial data** via Open Banking aggregators (Mono/Okra), who already hold CBN Open Banking registration

The honest, defensible one-line answer to "who's licensed here": *"We don't verify identity or hold financial data ourselves — we consume NIMC's national identity infrastructure and Mono/Okra's CBN-licensed Open Banking APIs, and issue Wema-specific reusable credentials on top."*

---

## 10. Competitive Landscape Summary

| Player | What They Do | How FOID Differs |
|---|---|---|
| Smile Identity, VerifyMe, IdentityPass, YouVerify | One-off KYC verification API, called per transaction | FOID is reusable/portable across products, not a per-call verification service |
| CreditChek, CrediSure, Indicina | Open-banking-based credit scoring for lenders | Credit signal is one input into a broader identity+trust persona, not the whole product; scoped to Wema's ecosystem, not sold as standalone lender infrastructure |
| NIMC (national identity layer) | Root identity authority, NIN, General Multipurpose Card | FOID consumes NIMC's infrastructure rather than competing with it; adds the financial-trust layer NIMC does not provide |

---

## 11. Success Metrics (for pitch/demo framing)

- Reduction in onboarding time for a returning FOID-verified user vs. a fresh KYC flow
- Reduction in manual review rate for low-risk, verified personas
- Cross-product activation rate (e.g. % of ALAT users who complete SME onboarding without repeating KYC)
- Time-to-detection for a credential state change vs. the manual review cycle it replaces (this is the clearest "before/after" number for the live demo — manual monitoring is periodic/human, FOID's is continuous/automatic)

---

## 12. Open Questions to Resolve Before Build

- Exact scope of claims issued in v1 (recommend starting with 3–5: identity_verified, bvn_validated, age_over_18, income_band, account_stability)
- Whether liveness/BVN/NIN checks are simulated/mocked for the hackathon demo (near-certain, given licensing/integration realities) vs. a real NIMC/BVN integration
- Consent UI — must visibly show what's being shared and to whom, every time, to make the "user-controlled" claim credible on stage
