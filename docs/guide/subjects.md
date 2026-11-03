# Subjects and consent

A **subject** is a person as your business knows them. Checks, verifications and Continue with FOID sign-ins all attach to a subject, and every read of a subject goes through the person's consent. Background: [Core concepts](./concepts#subjects).

## List and read subjects

| Endpoint | SDK | Returns |
|---|---|---|
| `GET /subjects?customer_ref=&limit=&offset=` | `request("GET", "/subjects", …)` | Your subjects, newest first |
| `GET /subjects/{id}` | `get_subject(id)` / `getSubject(id)` | One subject, filtered by the scopes you hold |
| `GET /subjects/{id}/checks` | `request()` | Every check result your consent still covers |
| `GET /subjects/{id}/trust-report` | `request()` | The trust report (scope `financial`) |
| `DELETE /subjects/{id}` | `request("DELETE", …)` | Erases the subject (`204`) |

::: code-group

```python [Python]
subject = foid.get_subject(subject_id)
checks = foid.request("GET", f"/subjects/{subject_id}/checks")
by_ref = foid.request("GET", "/subjects", params={"customer_ref": "cust_1001"})
```

```js [Node]
const subject = await foid.getSubject(subjectId)
const checks = await foid.request('GET', `/subjects/${subjectId}/checks`)
const byRef = await foid.request('GET', '/subjects', { params: { customer_ref: 'cust_1001' } })
```

:::

A subject only shows what its scopes allow:

| Always | `profile` or `identity` | `identity` | `contact` | `liveness` |
|---|---|---|---|---|
| `id`, `customer_ref`, `env`, `consent` (`status`, `scopes`), `has_foid_account`, `created_at` | `first_name`, `middle_name`, `last_name` | `date_of_birth`, `nin` and `bvn` as `{verified, last4}` | `email`, `phone` (masked) | `liveness.passed_at` |

`consent.status` is `active`, `revoked`, or `none` (nothing granted yet). Full responses: [`GET /subjects/{id}`](/api/reference#get-subjects-subject-id).

## Trust report {#trust-report}

For people with a FOID account who granted you the `financial` scope, the trust report gives verified signals about their identity and connected financial data, and the current **credential state**:

```json
{
  "object": "trust_report",
  "subject_id": "…",
  "credential_state": "active",
  "income_band": "high",
  "account_stability": "stable",
  "repayment_reliability": "…",
  "verification_completeness": 75,
  "verifications": { "email_verified": true, "nin_verified": true, "bvn_validated": true, "identity_verified": true, "phone_verified": false, "bill_verified": false },
  "signals": [{ "message": "…", "change": "active → under_review", "reason": "…", "at": "…" }],
  "last_refreshed_at": "…",
  "disclaimer": "Verified signals only. FOID does not score creditworthiness or recommend lending decisions."
}
```

- `credential_state` is `active`, `under_review`, `downgraded` or `revoked`.
- `verification_completeness` (0–100) is how much of the person's identity is verified on FOID.
- `signals` lists dated changes to the credential state.

The report is a set of verified signals, **not a score and not a recommendation**. Any decision stays with you.

| Error | When |
|---|---|
| `403 scope_not_granted` | You don't hold an active `financial` grant for this person. |
| `403 consent_revoked` | The person revoked your access. |
| `409 no_foid_account` | The subject isn't a FOID account holder. |
| `404 credential_not_found` | The person has no FOID credential yet. |

Subscribe to `credential.state_changed` to hear when the state changes. It's sent only to businesses holding an active `financial` grant.

## When a person revokes consent {#when-a-person-revokes-consent}

A person with a FOID account can revoke your access at any time from **Connected apps** in their FOID app. Immediately:

- `GET /subjects/{id}` and `/checks` return `403 consent_revoked`.
- `GET /verifications/{id}` still shows `status` and `outcome`, but each result becomes `{"status": "…", "redacted": true}`.
- Queued webhooks about that person are **cancelled** and can't be re-sent.
- You get exactly one `consent.revoked` webhook with the revoked scopes, who revoked and when.

Stop using the person's data and delete what you hold, under your own obligations (NDPA 2023).

## People who aren't on FOID (yet)

You can verify anyone; they don't need a FOID account. If the person later joins FOID, their subject is linked to the new account only with strong evidence: the NIN you verified must match theirs, **and** either their verified FOID email matches the email you recorded, or their FOID face matches the liveness face you captured. A typed NIN alone is never enough.

Once linked:

- They see your business in **Connected apps** and can revoke.
- You get a `subject.linked` webhook, and `has_foid_account` becomes `true`.
- You get **no new data**. To read FOID-held data (such as the trust report), ask in a new verification or a Continue with FOID sign-in, and they approve.

Test-mode subjects are never linked to real FOID accounts automatically.

## Delete a subject

`DELETE /subjects/{id}` erases the subject and everything FOID holds about it **for your business**: check results, the liveness face, consent records. Pending webhooks about the subject are cancelled. It returns `204` with no body; reading the subject afterwards gives `404 subject_not_found`.

::: code-group

```python [Python]
foid.request("DELETE", f"/subjects/{subject_id}")   # returns None
```

```js [Node]
await foid.request('DELETE', `/subjects/${subjectId}`)   // resolves to null
```

:::

This doesn't touch the person's own FOID account, or other businesses' subjects.
