# Test and live mode

Every organisation has a **test** and a **live** environment. Switch between them with the Test / Live toggle in the console sidebar. In Test mode the console shows an orange strip, so sandbox data is never mistaken for real customers.

## Test mode

Test mode is for building and demos:

- **Free.** Test checks are never billed.
- **Everything passes with sandbox data.** No real registry (NIMC, NIBSS) is contacted. Responses have the same shape as live, so your code works unchanged when you switch.
- **Available immediately** after you sign up. No business verification needed.
- **Separate data.** Test keys, sign-in apps, webhooks and subjects are invisible to live, and the other way round.

### Sandbox numbers

For NIN and BVN checks, the **last digit** of the 11-digit number decides the result:

| Last digit | Result |
|---|---|
| `0` – `7` | Found. The record echoes the name and date of birth you sent, so it `passed`. |
| `8` | Found under a different name: `failed`, reason `name_mismatch` |
| `9` | `failed`, reason `not_found` |

A number that isn't exactly 11 digits is refused with `400 invalid_nin` / `invalid_bvn`, as in live.

### Hosted verification in test mode

The hosted page shows a **Sandbox** badge. NIN and BVN steps follow the sandbox numbers above. The liveness step is a real camera check, so use your own face.

### Continue with FOID in test mode

Sign-in is the one thing in test mode that is **real**, like "Sign in with Google" in a test project:

- Any FOID user can sign in to your test app, with their own email and one-time code.
- The consent screen is clearly marked **Test app — not checked by FOID**.
- Your server gets the person's **real first and last name** only. Everything else is sandbox data in the live shape: date of birth `1990-01-01`, NIN last 4 `0001`, BVN last 4 `0002`, email `sandbox.person@example.com`, phone `+2348000000001`, and liveness "passed now".
- There's no face re-match in test mode.

You see what sign-in looks like end to end without receiving anyone's real identity data. Try it in the [Playground](/playground).

### localhost

Test sign-in apps accept `http://localhost:<any port>` and `http://127.0.0.1:<any port>` as origins and redirect URIs **without registering them**. Your local dev server just works. Registered `https://` URLs work too.

Test webhook endpoints may also use `http://localhost` / `http://127.0.0.1`, so you can receive webhooks on your machine. See [Webhooks: allowed URLs](./webhooks#allowed-urls).

## Live mode

Live mode uses real identity providers and real data:

- **Billed** per check (checks with `status: "error"`, for example a provider outage, are not billed).
- **Live API keys** (`FOID_LIVE_…`), live sign-in apps and live webhooks are separate from your test ones.
- **https only**: sign-in app origins, redirect URIs and webhook URLs. No localhost.
- **Continue with FOID** shares real data, and the person does a quick face re-match the first time they share with you.
- **IP allow-list** (optional): if you set one in Settings, live API keys only work from those addresses.

### Turning live mode on (KYB)

Live mode is locked until FOID verifies your business (KYB):

1. In the console, open **Go live** and submit your business details (CAC registration number, TIN, registered address) and the required documents.
2. FOID reviews them. You keep building in test mode meanwhile. The owners are emailed when the review is done.
3. Once approved, you can create live API keys and live sign-in apps.

Before that, live calls are refused with `403 live_mode_disabled`. The full checklist is in [Going live](./going-live).
