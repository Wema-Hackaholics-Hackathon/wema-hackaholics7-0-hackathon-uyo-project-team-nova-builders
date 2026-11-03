---
title: Playground
aside: false
---

# Playground

This is the real `<ContinueWithFoid>` button from [`@foid/react`](/sdks/react), wired to a FOID **test app** that FOID runs for these docs. Change the options on the left, click the button, and go through the real FOID window. The result you see is exactly what **your server** would get back from `foid.oauth.exchange()`.

<FoidPlayground />

## What you're seeing

- **The popup** is FOID's real sign-in: your FOID email, a one-time code, then a consent screen listing what's being shared. It's labelled *Test app — not checked by FOID* because this is test mode.
- **The result** has your **real first and last name** and **sandbox data for everything else** (NIN/BVN status, last 4 digits, date of birth, liveness, contact). That's how every test app works — see [Test and live mode](/guide/test-and-live).
- **Errors** — press *Cancel* (`access_denied`) or close the window (`popup_closed`) to see what your `onError` receives.
- **No FOID account yet?** The popup offers to verify you as a new person and, if you want, save it as a FOID. Or [create one first](/help/getting-started).

The docs app appears in your FOID app under **Connected apps** like any business you share with — you can remove it there.

::: tip Build it yourself
The snippets on the right are complete. For a full working app (React front end + Python or Node back end, every SDK feature) see the [Harbor example app](/sdks/example-app).
:::

::: details Running these docs locally
The playground talks to a FOID backend. From the repo: start `backend` (port 8000) and `frontend` (port 5173), then `cd docs && pnpm dev`. The docs dev server proxies `/api` to the backend. The backend creates the docs test app on first use; switch it off with `DOCS_PLAYGROUND=false`.
:::
