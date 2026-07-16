# FOID — Pitch FAQ
### Every question the presenter should be ready for, technical and general

**How to use this document:** Skim Section A first — it's your rehearsed core answer for the single most likely question. Sections B–J are organized by category so you can jump to whatever a judge is circling. If you only have time to memorize one thing before the pitch, memorize the answer in Q1.

---

## A. The Core Pitch — Get This One Perfect

**Q1: What happens after the Open Banking API connects? (This will be asked. Rehearse this exact answer.)**
The connection doesn't end at reading data once. It stays live. FOID keeps watching the transaction feed, and the moment something meaningful happens — income drops, a repayment bounces — FOID automatically changes the state of the person's credential itself, in real time, with no human reviewing a dashboard. That update instantly propagates to every product using that persona, and the user is notified of exactly what changed and why. The "intelligent action" is the credential updating itself, not a person reading a report and deciding to act.

**Q2: What is FOID, in one sentence?**
A reusable, verified financial identity — built once, updated continuously from real bank behavior, shared with consent across every Wema product a person touches.

**Q3: What problem does this solve?**
Every financial product a Nigerian signs up for repeats the same KYC ritual from zero — BVN, NIN, liveness, manual review — even if they were fully verified somewhere else last week. And once verified, that status is frozen; nobody re-checks whether the person is still a good risk until they've already defaulted. FOID fixes both: verify once, reuse everywhere within Wema, and keep the financial trust signal current automatically.

**Q4: Why does this matter to an ordinary person, not just a bank?**
Faster onboarding across every Wema product they touch, less repeated document upload, and — because their good financial behavior is recognized continuously instead of only at signup — access to better terms and limits sooner than a static, one-time credit check would give them.

---

## B. "Why Not X" — Competitive & Regulatory Defense

**Q5: Isn't this what NIMC already does under the new NIMC Act 2026?**
NIMC verifies *who someone is* — NIN, liveness, the General Multipurpose Card. FOID doesn't compete with that; it consumes it. What NIMC's identity layer doesn't and won't provide is a *financial trust signal* — that requires reading real bank transaction behavior, which is Open Banking's job, not NIMC's. FOID is the layer on top of NIMC's identity infrastructure, not a replacement for it.

**Q6: How is this different from CreditChek or Indicina?**
They compute a credit score at a single point in time, when asked. FOID never computes a credit score or a lending recommendation at all — that decision stays entirely with the lender. What FOID issues is a living credential that updates its own state continuously as real behavior changes. Different technical shape, different output, and FOID deliberately never touches the underwriting decision itself.

**Q7: How is this different from Smile Identity, VerifyMe, IdentityPass, or YouVerify?**
Those are one-off KYC verification APIs — a fintech calls them once per new user, gets a pass/fail, and that's the end of the relationship. FOID is portable and reusable: verify once, and every subsequent Wema product reuses the same verified persona instead of re-running verification from scratch.

**Q8: What stops Wema from just building this internally instead of you?**
Nothing stops a well-resourced bank from building any of this eventually — that's true of almost any B2B infrastructure pitch. The realistic argument isn't "Wema can't," it's "Wema hasn't, and won't prioritize it ahead of core banking roadmap items unless someone brings them a working system." A hackathon-validated prototype changes the calculus from "should we build this someday" to "this already exists, should we adopt it now."

**Q9: What stops a competing bank from copying this?**
Nothing legally distinctive prevents a technical clone. The defensibility isn't a patent — it's the same kind of moat credit bureaus have: the more relying parties and users on the persona layer, the more current and valuable the trust signal becomes. A first-mover with real usage data has a structurally better signal than a fast-follower with none.

**Q10: Is "digitizing KYC/identity" already saturated in Nigeria the way ajo, SME bookkeeping, and loan comparison apps turned out to be?**
This was checked directly and deliberately, because every prior idea in this process failed exactly this test. Existing players (Smile ID, VerifyMe, YouVerify) all operate as one-off verification APIs, not portable/reusable credential systems. No confirmed player was found doing continuous, self-updating financial trust credentials at the time of this research. This should be re-verified periodically, not assumed permanently true.

---

## C. Business Model & Market

**Q11: How does FOID make money?**
Primarily a B2B SaaS model — Wema (and eventually other relying parties) pay per verified persona, per credential check, or on a tiered subscription basis tied to volume. This mirrors how credit bureaus and KYC-as-a-service providers are already priced in this market.

**Q12: What's the market size?**
Every Wema product line — ALAT retail, SME accounts, lending, and any embedded partner products — is a potential consumer of FOID credentials. The realistic near-term market is internal to Wema's own ecosystem; the longer-term, larger market is other relying parties (other lenders, insurers, landlords) once the model proves out — but that expansion is explicitly out of scope for the hackathon pitch itself (see Q13).

**Q13: Is the ambition really just "inside Wema," or bigger?**
The hackathon pitch is deliberately scoped to Wema's own ecosystem — that's the defensible, buildable claim. "Wema becomes the trust layer other institutions plug into" is a legitimate longer-term vision, but pitching that scale on day one invites exactly the kind of national-infrastructure scrutiny that already killed two earlier ideas in this process (the escrow custody idea and the credit-bureau idea). Undersell the ambition, overdeliver the mechanism.

**Q14: What does Wema get out of this that they don't already have?**
Lower cost per onboarded customer (fewer manual KYC reviews), higher conversion (less onboarding friction across products), better risk decisions using a signal that's always current instead of one that's stale the moment it's checked, and a genuine cross-sell advantage — a verified ALAT user becomes a near-instant approval candidate for an SME account or loan product.

---

## D. Legal, Licensing & Compliance

**Q15: Who is legally responsible for the money or data here — is FOID a licensed institution?**
No. FOID never becomes a licensed financial institution, never custodies user funds, and never performs payment initiation in this version. It's a read-only consumer of two already-licensed data sources: NIMC's national identity infrastructure for identity data, and CBN-licensed Open Banking aggregators (Mono/Okra) for financial data.

**Q16: What's the one-line answer if a judge asks "who's licensed to do this"?**
"We don't verify identity or hold financial data ourselves — we consume NIMC's national identity infrastructure and Mono/Okra's CBN-licensed Open Banking APIs, and issue Wema-specific reusable credentials on top."

**Q17: Does FOID comply with Nigeria's data protection law (NDPA)?**
The design is built around purpose-limited, consent-based data sharing by construction — relying parties only ever see specific bounded claims (e.g. "income band," "BVN validated"), never raw transaction statements or documents. That data-minimization approach is directly aligned with NDPA principles, though a real deployment would still need formal legal review before launch — this FAQ isn't a substitute for that.

**Q18: What CBN rules is this built around?**
The 2026 CBN KYC directives require liveness checks, real-time BVN/NIN validation, and stronger device binding for online onboarding — all of which raise the cost of KYC per institution, which is exactly what makes reusable, once-verified credentials valuable. FOID is designed to encode proof that these CBN-mandated checks were performed, not to bypass or weaken them.

**Q19: Who owns the credential — the user, Wema, or FOID?**
The user. Credentials live in the user's own wallet/persona, and they choose what to share and with whom via a consent screen every time. This is a deliberate design principle, not a technicality — it's what makes "user-controlled" a true claim rather than a slogan.

**Q20: Can a user revoke access once granted?**
Yes — this is a stated design requirement, not an afterthought. A user can revoke a relying party's access to their credentials at any time; this should be visibly demoable if a judge asks to see it.

---

## E. Technical Architecture & Mechanics

**Q21: What's the actual data flow, step by step?**
(1) User completes liveness + BVN/NIN check and connects their bank account via Open Banking (Mono/Okra sandbox for the demo). (2) FOID issues signed, verifiable claims covering identity and financial attributes. (3) User applies to a Wema product; a consent screen shows exactly which claims are requested; user approves or declines. (4) The relying party verifies the credential's signature and current state — no document re-upload, no manual review for already-verified attributes. (5) With ongoing consent, FOID keeps monitoring the live transaction feed and auto-updates credential state on defined triggers.

**Q22: What technical standard are the credentials built on?**
Signed, verifiable claims — conceptually aligned with W3C Verifiable Credentials / OpenID Connect for Verifiable Presentations (OIDC4VP) patterns. For a hackathon build, this can be implemented as signed JWTs without needing a full production-grade VC stack.

**Q23: What specific claims does FOID issue in v1?**
Deliberately minimal: `identity_verified`, `bvn_validated`, `age_over_18`, `income_band`, `account_stability` (or `repayment_reliability`, depending on final demo scope). Starting with 3–5 claims that unblock 1–2 real product flows, not trying to model everything on day one.

**Q24: What Open Banking provider are you using, and why?**
Mono or Okra — both are CBN-licensed Nigerian account aggregators with sandbox environments suitable for a hackathon build. Using a licensed aggregator (rather than building direct bank integrations) is also what keeps FOID out of needing its own financial data-handling license.

**Q25: Is the AI/LLM layer doing anything safety-critical?**
No, and this is intentional. Core logic — consent flows, credential issuance rules, KYC policy enforcement, state-change triggers — is deterministic and rule-based, not AI-generated, so it stays auditable and explainable. Any AI/LLM use (e.g. conversational onboarding guidance, transaction categorization for messy merchant names) sits on top of that deterministic core as a UX enhancement, never as the thing making a trust or compliance decision.

**Q26: What happens if the Open Banking API (Mono/Okra) goes down?**
Existing credentials remain valid at their last known state — FOID doesn't invalidate everything just because the live feed is temporarily unavailable. New state updates simply pause until the connection is restored; this should be a stated fallback behavior, not something judges discover by asking a question you haven't thought about.

---

## F. The Living Credential Mechanism — Deep Dive

**Q27: Walk me through exactly how a credential's state changes.**
Every issued credential has a state field (`active`, `under_review`, `downgraded`, `revoked`), not just a static value. The system defines specific trigger conditions on the transaction feed — e.g. a defined drop in expected income, or a recurring repayment debit failing. When a trigger fires, the credential's state updates automatically, no human in the loop, and the change is pushed to any relying party currently holding that credential.

**Q28: What exactly counts as a "trigger" — how sensitive is it?**
For the hackathon demo, triggers are simple and rule-based (a defined threshold — e.g. an expected recurring credit failing to appear, or a known repayment debit bouncing) rather than ML-driven. This is a deliberate choice: rule-based triggers are auditable, explainable, and reliable to demo live, whereas an ML model risks misfiring unpredictably on stage.

**Q29: What happens to the user when their credential is downgraded?**
They're notified immediately — what changed, why, and what they can do about it. This is a hard requirement, not optional: a silent downgrade would make FOID look like invisible surveillance rather than transparent, user-controlled infrastructure, which would undercut the entire consent-based premise of the pitch.

**Q30: Can a downgrade be wrong — false positives?**
Yes, this is a real risk with any automated trigger system, and it should be acknowledged rather than glossed over. Mitigations: keep triggers conservative and rule-based rather than aggressive; give the user a visible way to contest or explain a downgrade; treat "downgraded" as "flagged for a closer look," not an automatic denial — the lending decision still sits with the relying party, who can weigh context FOID doesn't have.

**Q31: Does a credential ever get upgraded again, or only downgraded?**
The design should support both directions — sustained good behavior (consistent repayment, income stabilizing) should be able to move a credential back toward a stronger state over time, not just flag deterioration. This is worth stating explicitly if asked, since a system that only ever downgrades would feel punitive rather than fair.

**Q32: How is this different from a simple webhook/alert system a bank could already build?**
The distinction is that the *credential itself* changes state and that state is what every relying party reads — it's not a notification sent to a human who then has to act on it. A basic alert system tells someone "check this." FOID's mechanism changes what "this" objectively *is*, automatically, and that new truth is what every downstream product sees the next time it looks.

---

## G. Data Privacy & User Trust

**Q33: What data does a relying party actually see?**
Only the specific bounded claims they request and the user approves — e.g. "income band: ₦150k–300k" — never raw transaction statements, account numbers, or full financial history. This selective disclosure is core to the design, not a privacy add-on.

**Q34: Does FOID store raw bank transaction data?**
The minimal defensible answer: FOID processes transaction data to compute bounded claims and monitor for triggers, but relying parties never receive raw data — only the resulting claims. Exact data retention policy (how long raw transaction data is held internally for monitoring purposes) is a real design decision that should be answered concretely before a production build, not left vague.

**Q35: What if a user doesn't want ongoing monitoring, just one-time verification?**
This should be a genuine user choice, not forced — a user could consent to one-time identity verification only, without opting into the continuous financial-monitoring layer, accepting that their financial claims simply won't self-update if they decline. Worth stating this as a design principle if asked, since forced ongoing surveillance would be a real trust problem.

---

## H. Demo Specifics — What's Real vs. Simulated

**Q36: What's actually functional in the live demo, and what's simulated?**
Real: the Open Banking sandbox connection (Mono/Okra), live transaction ingestion, the credential state machine, the real-time push/sync between the user-facing app and the relying-party view, and the consent UI. Simulated, and stated openly on stage rather than hidden: actual NIMC/BVN/NIN verification (framed as "in production, this runs through Wema's existing licensed KYC provider") and the trigger event itself, since a real missed-payment cycle can't be waited out live.

**Q37: Why is it okay to simulate parts of the demo?**
Being upfront about what's real versus simulated is a credibility move, not a weakness — judges have seen enough hackathon demos to know full production integration in a weekend isn't realistic, and pretending otherwise (and getting caught) is far worse than stating the boundary confidently.

**Q38: What's the actual demo script?**
(1) Persona creation — liveness/BVN/NIN + bank connection, ~45 seconds. (2) Selective disclosure — user applies to a mock Wema loan product, consent screen shown, relying-party view populates instantly, ~45 seconds. (3) The centerpiece — inject a simulated missed-repayment event via a visible "demo control panel," and show both the user notification and the relying-party credential state flip in real time, side by side, ~60–90 seconds. (4) Close — tie back to Wema's benefit and the NIMC/licensing positioning, ~30 seconds.

---

## I. Risk & Edge Cases

**Q39: What's the single biggest risk to this idea, honestly?**
That the differentiation from CreditChek/Indicina/Smile ID collapses if FOID's scope creeps into computing scores or recommendations — this has already been flagged and deliberately designed against (see §8/Non-Goals in the PRD), but it's a boundary that has to be actively maintained, not something solved once and forgotten.

**Q40: What if NIMC's own infrastructure eventually adds a financial-trust layer too?**
That's a real long-term risk worth naming honestly rather than dismissing. The near-term defense is that NIMC's mandate under the 2026 Act is explicitly about identity (who someone is), not financial behavior — building and operating continuous financial-behavior monitoring is a fundamentally different kind of infrastructure than identity verification, and there's no current signal NIMC is moving in that direction.

**Q41: What if a relying party ignores a downgrade and lends anyway?**
That's their prerogative and their risk — FOID provides the signal, not the decision. This should be stated plainly: FOID is infrastructure, not a compliance enforcer, and relying parties retain full discretion over how they use the credential.

**Q42: What happens if the user closes the bank account FOID is monitoring?**
The financial trust layer would lose its live data source — the identity layer remains valid, but financial claims would need to either freeze at last-known state (clearly marked as stale) or require the user to reconnect an account. This is a real product decision worth having an answer for, even if simplified for the demo.

---

## J. Investor-Lens Questions

**Q43: What's the actual moat here, in investor terms?**
A data-network effect structurally similar to why credit bureaus exist: the more relying parties and users on the persona layer, the more current and valuable the aggregate trust signal becomes, versus any single institution's isolated view of a borrower. That's a real, defensible answer — but it only becomes true with real usage, not on day one.

**Q44: Is this a big enough business to matter, or just a nice internal tool for Wema?**
Scoped honestly for the hackathon, it's the latter — a genuinely valuable internal tool for Wema. The larger business case (other relying parties adopting Wema-issued credentials) is a real, plausible future, but it should be framed as a roadmap ambition, not the current pitch — overclaiming scale here is what triggers the "isn't this just NIMC's job" pushback.

**Q45: What would you need to prove, post-hackathon, to justify further investment?**
Real reduction in onboarding time and manual review rate for actual Wema users, evidence that the living-credential mechanism catches real deteriorating-risk cases earlier than the current manual process, and at least one additional relying party (internal Wema product or an external partner) successfully consuming the credential to prove the reuse model works beyond a single product.

---

## Quick-Reference Cheat Sheet

If time is short before the pitch, these five answers cover the highest-probability questions:

1. **"What happens after the API connects?"** → The connection stays live; the credential updates its own state automatically from real behavior, with no human review.
2. **"Isn't this NIMC's job?"** → NIMC verifies identity; FOID adds the financial-trust layer NIMC doesn't provide, built on Open Banking, not NIN.
3. **"How is this different from CreditChek?"** → They score at a point in time; FOID never scores at all — it issues a living credential that updates itself, and the lending decision always stays with the relying party.
4. **"Who's licensed to do this?"** → Nobody at FOID needs to be — it consumes NIMC's identity infrastructure and Mono/Okra's already-licensed Open Banking APIs, never touching funds or raw identity verification itself.
5. **"What's real in this demo?"** → The Open Banking connection, the state machine, and the live sync are real; NIMC/BVN verification and the trigger event are simulated, and that's said out loud, not hidden.
