# Contributing to FOID

Quick reference for how we work together on this repo. Read this once, takes two minutes.

## Golden Rule

**Nobody pushes straight to `main`.** Everything goes through a branch and a PR, even small changes. This is what keeps a hackathon build from turning into a merge-conflict mess two hours before demo time.

## Branch Naming

Use this pattern so it's obvious what a branch is for at a glance:

```
<type>/<short-description>
```

Types:
- `feature/` — new functionality (e.g. `feature/consent-screen`)
- `fix/` — bug fixes (e.g. `fix/credential-state-sync`)
- `demo/` — anything specific to the pitch/demo build (e.g. `demo/control-panel-trigger`)
- `docs/` — README, PRD, FAQ updates (e.g. `docs/faq-licensing-section`)

## Workflow

1. **Pull latest `main`** before starting anything: `git pull origin main`
2. **Create your branch** off `main`: `git checkout -b feature/your-thing`
3. **Commit as you go**, with messages that say what changed, not just "fix" or "update":
   - Good: `add consent screen for claim sharing`
   - Not great: `changes`
4. **Push your branch**: `git push origin feature/your-thing`
5. **Open a PR into `main`** — write 2-3 lines on what it does and why. Doesn't need to be formal, just enough that someone else understands it without asking you.
6. **Get at least one review before merging**, if humanly possible in our timeframe. If we're under real time pressure and nobody's free to review, say so in the team chat before merging solo — don't merge silently.
7. **Delete the branch after merging** to keep things clean.

## PR Checklist (quick, not bureaucratic)

Before opening a PR, check:
- [ ] Does it run locally without errors?
- [ ] Did you pull the latest `main` recently, so this isn't wildly out of date?
- [ ] If it touches scope (see below), does it actually belong in this project?

## Scope Guardrail — Check This Before You Build, Not After

FOID has a few deliberate, non-negotiable boundaries from the PRD. If your feature touches any of these, flag it in the team chat *before* you write the code, not in a PR review after:

- **No credit scoring, affordability scores, or loan recommendations.** FOID issues claims; it never makes or suggests a lending decision.
- **No custody of funds.** Read-only Open Banking access, non-custodial, always.
- **No bookkeeping/analytics dashboards.** That idea was deliberately cut — see the PRD if you're unsure why.
- **No competing with NIMC's identity role.** We consume their infrastructure, we don't replace it.

If you think one of these boundaries should flex for a good reason, that's a real conversation to have — just have it with the team first, not as a surprise in a merge.

## Commit Message Style

Keep it short and in plain English, present tense:
- `add liveness check UI`
- `fix state-sync delay between user app and relying-party view`
- `update PRD non-goals section`

## Conflicts / Stuck?

If you hit a merge conflict you're not sure how to resolve, don't force-push over someone else's work — ask in the team chat first. Losing a teammate's work two hours before a deadline is a much bigger problem than a delayed merge.

## Who to Ask

If you're unsure whether something fits FOID's scope, check `/docs/FOID_PRD.md` first — most "should we add X" questions have already been thought through there. If it's still unclear, ask the team before building, not after.
