# Quickstart

Make your first FOID API call in about five minutes, in test mode. Nothing here touches real identity data or costs money.

## 1. Create a console account

Sign up in the FOID console with your work email and company name, then enter the 6-digit code FOID emails you. Signing up creates your **organisation**, and the console opens in **Test mode** (an orange strip across the top).

## 2. Create a test API key

Go to **API keys & webhooks**, then **Create key**, with the console in Test mode. Copy the key: it starts with `FOID_TEST_` and is shown **once**. FOID only stores a hash of it.

Keep it on your server, for example in an environment variable:

```bash
export FOID_API_KEY=FOID_TEST_…
```

## 3. Call the API

`GET /ping` checks that your key works.

::: code-group

```bash [curl]
curl https://api.foid.ng/api/open/v1/ping \
  -H "Authorization: Bearer $FOID_API_KEY"
```

```python [Python]
import os
from foid import Foid

foid = Foid(api_key=os.environ["FOID_API_KEY"])
print(foid.request("GET", "/ping"))
```

```js [Node]
import { Foid } from '@foid/node'

const foid = new Foid({ apiKey: process.env.FOID_API_KEY })
console.log(await foid.request('GET', '/ping'))
```

:::

```json
{ "ok": true, "organisation": "Acme Wallet", "env": "test" }
```

Running FOID yourself? Use `http://localhost:8000` as the base URL: `baseUrl` in Node, `base_url` in Python. The SDKs default to `https://api.foid.ng`. To install the SDKs, see [SDKs](/sdks/).

## 4. Run a check

Look up an NIN and match it against the name you hold. In test mode the **last digit** of the number decides the result: `0`–`7` pass, `8` is a name mismatch, `9` is not found. See [Test and live mode](./test-and-live#sandbox-numbers).

::: code-group

```bash [curl]
curl https://api.foid.ng/api/open/v1/checks/nin \
  -H "Authorization: Bearer $FOID_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "number": "12345678901",
    "first_name": "Ada", "last_name": "Obi", "date_of_birth": "1994-03-12",
    "customer_ref": "cust_1001",
    "consent": { "obtained": true, "purpose": "Account opening" }
  }'
```

```python [Python]
result = foid.check_nin(
    number="12345678901",
    first_name="Ada", last_name="Obi", date_of_birth="1994-03-12",
    customer_ref="cust_1001",
    consent={"obtained": True, "purpose": "Account opening"},
)
print(result["status"], result["data"]["nin_last4"])   # passed 8901
```

```js [Node]
const result = await foid.checkNin({
  number: '12345678901',
  first_name: 'Ada', last_name: 'Obi', date_of_birth: '1994-03-12',
  customer_ref: 'cust_1001',
  consent: { obtained: true, purpose: 'Account opening' },
})
console.log(result.status, result.data.nin_last4)   // passed 8901
```

:::

`consent.obtained: true` is your statement that the person agreed to this check. FOID records it. The response includes a `subject_id`, FOID's ID for this person at your business. The full response is in the [API reference](/api/reference#post-checks-nin).

## 5. Or start a hosted verification

When you also want a liveness check, or prefer FOID to collect consent, create a verification and send the person to its `hosted_url`:

::: code-group

```python [Python]
v = foid.create_verification(
    checks=["nin", "liveness"],
    purpose="Open a wallet",
    customer_ref="cust_1001",
    first_name="Ada", last_name="Obi",
    return_url="https://acme.example/kyc/done",
    idempotency_key="onboard-cust_1001",
)
print(v["hosted_url"])   # send the person here
```

```js [Node]
const v = await foid.createVerification({
  checks: ['nin', 'liveness'],
  purpose: 'Open a wallet',
  customer_ref: 'cust_1001',
  first_name: 'Ada', last_name: 'Obi',
  return_url: 'https://acme.example/kyc/done',
  idempotencyKey: 'onboard-cust_1001',
})
console.log(v.hosted_url)   // send the person here
```

:::

## Next

- Add a sign-in button: [Continue with FOID](./continue-with-foid), or try it first in the [Playground](/playground).
- Get told when things finish: [Webhooks](./webhooks).
- See every SDK feature working: the [Harbor example app](/sdks/example-app).
