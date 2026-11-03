# Going live

Everything you build in test mode works in live mode with live credentials. Live mode adds real data, billing, and stricter rules.

## 1. Verify your business (KYB)

Live mode is locked until FOID approves your business. In the console, open **Go live**:

1. Fill in your business details: CAC registration number (RC), TIN and registered address.
2. Upload the required documents.
3. Submit. FOID reviews them and emails your organisation's owners with the result. If something is missing, the review note says what.

Until approval, live calls are refused with `403 live_mode_disabled`, and you can't create live API keys or live sign-in apps.

## 2. Create live credentials

Switch the console to **Live**, then:

| Credential | Where | Notes |
|---|---|---|
| Live API key (`FOID_LIVE_…`) | API keys & webhooks | Shown once. Store it in your secret manager, not in code. |
| Live sign-in app (`foid_app_live_…`) | Sign-in apps | Exact `https://` origins and redirect URIs. No localhost. Prefer a [key pair](./continue-with-foid#key-pair-private-key-jwt). |
| Live webhook endpoint | API keys & webhooks | `https://` only, public address. See [allowed URLs](./webhooks#allowed-urls). |

Then point your production config at them. Nothing else in your code changes: responses have the same shape in both modes.

## 3. What changes in live

- **Real lookups.** NIN / BVN checks go to the identity provider; there are no sandbox numbers.
- **Billing.** Each check is billed (checks with `status: "error"` are not). See **Usage & Billing** in the console.
- **Continue with FOID** shares the person's real verified data. The first time a person shares with you, they do a quick face re-match. People missing a required step (liveness enrolment, or NIN when you ask for `identity`) complete it in the popup.
- **Stricter URLs.** https only, everywhere.

## 4. Lock it down

- **IP allow-list.** In **Settings**, restrict live API keys to your servers' IP addresses or CIDR ranges. Calls from anywhere else get `403 ip_not_allowed`. This applies to live API keys, not to test keys or the token endpoint.
- **Two-step sign-in for the team.** In **Settings**, require every team member to use an authenticator app to open your organisation.
- **Key creation alerts.** Owners and admins are emailed when an API key is created (on by default, in **Settings**).
- **Least privilege.** Give teammates the lowest role that works (**Team**). Developers can manage keys and webhooks.
- **Rotate secrets.**
  - API keys: create the new key, deploy it, then revoke the old one.
  - Client secrets: rotate in **Sign-in apps**. The old secret keeps working for 24 hours so you can deploy without downtime.
  - Webhook signing secrets: roll from the endpoint. Deploy the new secret right away.

## 5. Monitor

- **Request logs** show every Open API call and token exchange, with its `FOID-Request-Id`.
- The webhook **delivery log** shows failures. Developers are alerted when an endpoint keeps failing.
- Your console notifications flag security events, such as a sign-in code used twice.

Before launch, run through the [Security checklist](./security).
