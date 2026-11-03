# Webhooks

FOID sends signed `POST` requests to your server when something happens: a verification finishes, a check completes, a person revokes consent. Use webhooks rather than polling, and to confirm anything a browser told you.

## Add an endpoint

In the console, open **API keys & webhooks** and add an endpoint, with the console in the environment you want (test or live). Choose the events (or all of them). The **signing secret** (`whsec_…`) is shown **once**. You can roll it later.

Each endpoint belongs to one environment. Test events never go to live endpoints.

## Events

| Event | When | `data` |
|---|---|---|
| `verification.completed` | A hosted verification finished | The verification (no `hosted_url` / `client_token`) |
| `verification.cancelled` | The person declined consent, or you cancelled | `{id, status, …}` (with `reason: "consent_declined"` when the person declined) |
| `verification.expired` | Nobody finished it before the link expired | `{id, status: "expired"}` |
| `check.completed` | A server-to-server check finished | The check result |
| `consent.revoked` | The person revoked your access | `subject_id`, `customer_ref`, `scopes`, `revoked_by`, `revoked_at` |
| `subject.linked` | A subject you verified was linked to a FOID account | `{subject_id, customer_ref, foid_account: true}` |
| `credential.state_changed` | A FOID credential changed state. Only sent if you hold the `financial` scope. | `subject_id`, `customer_ref`, `previous_state`, `credential_state`, … |
| `webhook.test` | You pressed **Send test** in the console | `{"message": "Hello from FOID"}` |

Every event has the same envelope:

```json
{
  "id": "evt_5b2c…",
  "type": "verification.completed",
  "env": "live",
  "created": 1793560000,
  "data": { "…": "…" }
}
```

Each request has these headers:

| Header | |
|---|---|
| `FOID-Signature` | `t=<unix seconds>,v1=<hex HMAC-SHA256>`. Verify it, see below. |
| `FOID-Event-Id` | The event `id`. Use it to ignore duplicates. |
| `Content-Type` | `application/json` |
| `User-Agent` | `FOID-Webhooks/1` |

## Verify the signature

The signature is an HMAC-SHA256 of `"<t>.<raw body>"` with your endpoint's signing secret. Always verify it on the **raw request body** (the exact bytes you received, not re-serialised JSON), and reject anything older than 5 minutes.

::: code-group

```python [Python (FastAPI)]
import os
from fastapi import FastAPI, HTTPException, Request
from foid import verify_webhook, WebhookError

app = FastAPI()
SECRET = os.environ["FOID_WEBHOOK_SECRET"]

@app.post("/webhooks/foid")
async def foid_webhook(request: Request):
    raw = await request.body()
    try:
        event = verify_webhook(raw, request.headers.get("FOID-Signature", ""), SECRET)
    except WebhookError:
        raise HTTPException(400, "bad signature")
    if event["type"] == "verification.completed":
        ...   # update your records, keyed by event["data"]["id"]
    return {"received": True}
```

```js [Node (Express)]
import express from 'express'
import { verifyWebhook } from '@foid/node'

const app = express()

// express.raw: the signature is over the exact bytes, so don't parse JSON first
app.post('/webhooks/foid', express.raw({ type: 'application/json' }), (req, res) => {
  let event
  try {
    event = verifyWebhook(req.body, req.get('FOID-Signature'), process.env.FOID_WEBHOOK_SECRET)
  } catch {
    return res.status(400).send('bad signature')
  }
  if (event.type === 'verification.completed') {
    // update your records, keyed by event.data.id
  }
  res.json({ received: true })
})
```

```python [Any language (raw HMAC)]
import hashlib, hmac, time

def verify(secret: str, header: str, raw_body: bytes, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    if abs(time.time() - int(parts["t"])) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

:::

The SDKs raise `WebhookError` (Python) or an `Error` (Node) when the header is missing or malformed, the timestamp is outside the tolerance (default 300 seconds), or the signature doesn't match. On success they return the parsed event.

## Delivery and retries

- Respond with any **2xx** within 10 seconds. Do the slow work afterwards.
- Anything else (non-2xx, timeout, connection error) is retried with backoff: after 10 s, 30 s, 2 min, 10 min, 30 min, 1 h and 3 h. After 8 failed attempts in total the delivery is marked **failed**, and your developers get an alert in the console.
- FOID doesn't follow redirects. Point the endpoint at the final URL.
- Deliveries can arrive more than once and out of order. De-duplicate on `FOID-Event-Id`, and read the current state from the API if order matters.

**Consent comes first.** A delivery about a person is cancelled at send time if you no longer hold an active consent grant for them, even if it was queued before they revoked. Those deliveries can't be re-sent. `consent.revoked` itself is always delivered.

## Delivery log, retry and test

In the console under **API keys & webhooks**, each endpoint shows its recent deliveries (status, attempts, last HTTP code, last error and payload). You can **retry** a delivery and **send a test** `webhook.test` event at any time.

## Allowed URLs {#allowed-urls}

A webhook URL is something FOID's server calls, so FOID checks it to make sure it can't be pointed at FOID's own network.

| | Test endpoints | Live endpoints |
|---|---|---|
| Scheme | `http://` or `https://` | `https://` only |
| `localhost`, `127.0.0.1`, `::1` | Allowed, so you can receive webhooks on your own machine. A FOID server with `ENV=production` refuses them unless `WEBHOOK_ALLOW_LOCALHOST=true`. | Refused |
| Private, link-local, carrier-grade NAT, reserved, multicast or unspecified addresses (`10.x`, `192.168.x`, `169.254.169.254`, `fd00::/8`, `0.0.0.0`, …) | Refused | Refused |
| Internal hostnames: single-label names (`intranet`) and `*.internal`, `*.local`, `*.localdomain`, `*.lan`, `*.home`, `*.corp`, `*.intranet`, `*.home.arpa` | Refused | Refused |
| A username or password in the URL | Refused | Refused |

A refused URL is rejected when you save it with `400 invalid_webhook_url` and a message saying why.

FOID checks again at **every delivery**: it resolves the hostname, refuses if **any** address is internal, and connects to the address it checked (the `Host` header and the TLS certificate check still use your hostname). A DNS record changed to an internal address after you saved the URL can't redirect deliveries. A refused delivery shows `blocked: …` as its last error.
