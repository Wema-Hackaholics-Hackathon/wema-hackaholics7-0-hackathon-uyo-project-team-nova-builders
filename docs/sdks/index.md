# SDKs

| Package | Runs on | What it does |
|---|---|---|
| [`foid`](./python) | Your server: Python ≥ 3.10 | Continue with FOID code exchange (client secret or key pair), the Open API, webhook verification, PKCE helpers, `python -m foid keygen` |
| [`@foid/node`](./node) | Your server: Node ≥ 18, no dependencies | The same as Python, for Node. `npx foid keygen` |
| [`@foid/react`](./react) | The browser | `<FoidProvider>`, the `<ContinueWithFoid>` button, `useFoidLogin()`, plus a framework-free core (`@foid/react/core`) |

The server SDKs hold your secrets. The React SDK only ever has your public **client ID**. A typical setup uses one of each: the button in your front end, and the server SDK in the endpoint that receives the code.

## Install

::: warning Not on PyPI / npm yet
The SDKs are not published to the public registries yet. Install them from the FOID repository, or from packed files.
:::

**From the repository** (with the FOID repo checked out next to your project):

::: code-group

```bash [Python]
pip install "./sdks/python[keypair]"       # or, in a uv project: uv add ./sdks/python --extra keypair
```

```bash [Node]
npm install ./sdks/node
```

```bash [React]
npm install ./sdks/react
```

:::

The `keypair` extra pulls in `cryptography`, which is only needed for key pairs (`private_key_jwt`) and `keygen`. Client-secret apps and the Open API need only `httpx`.

**From packed files.** This is how the [Harbor example app](./example-app) does it, as if the SDK came from a registry:

```bash
# from the FOID repo; OUT is a vendor/ folder in your project
OUT=/path/to/your-project/vendor
(cd sdks/python && uv build --wheel -o "$OUT")          # foid-0.1.0-py3-none-any.whl
(cd sdks/node   && npm pack --pack-destination "$OUT")  # foid-node-0.1.0.tgz
(cd sdks/react  && npm pack --pack-destination "$OUT")  # foid-react-0.1.0.tgz
```

Then depend on the file: `"@foid/node": "file:vendor/foid-node-0.1.0.tgz"` in `package.json`, or `foid = { path = "vendor/foid-0.1.0-py3-none-any.whl" }` under `[tool.uv.sources]`.

## Configuration

The server SDKs default to the hosted API at `https://foid-iy7u.onrender.com`. When you run FOID yourself, pass the base URL:

::: code-group

```python [Python]
from foid import Foid
foid = Foid(api_key="FOID_TEST_…", base_url="http://localhost:8000")
```

```js [Node]
import { Foid } from '@foid/node'
const foid = new Foid({ apiKey: 'FOID_TEST_…', baseUrl: 'http://localhost:8000' })
```

:::

The React SDK defaults to `https://usefoid.pages.dev` for the popup. Pass `foidUrl="http://localhost:5173"` to `<FoidProvider>` locally.

## Which credential goes where

| Credential | Python | Node | React |
|---|---|---|---|
| API key (`FOID_TEST_…`) | `api_key=` | `apiKey` | never |
| Client ID (`foid_app_…`) | `client_id=` | `clientId` | `<FoidProvider clientId>` |
| Client secret (`foid_cs_…`) | `client_secret=` | `clientSecret` | never |
| Private key PEM | `private_key_pem=` | `privateKeyPem` | never |
| Webhook secret (`whsec_…`) | `verify_webhook(…, secret)` | `verifyWebhook(…, secret)` | never |

One client object can hold several credentials. It uses the API key for the Open API, and the client secret or private key for `oauth.exchange`. See [Keys and credentials](/guide/concepts#keys-and-credentials).

## See it working

- [Playground](/playground): the real button, in your browser.
- [Harbor example app](./example-app): a complete app with a React front end and a Python or Node back end, exercising every SDK feature.
