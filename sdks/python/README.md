# FOID SDKs

| Package | Where | What |
|---|---|---|
| `foid` (Python ≥ 3.10) | `sdks/python` | Server: Continue with FOID code exchange (client secret or key pair), Open API calls, webhook signatures, `python -m foid keygen` |
| `@foid/node` (Node ≥ 18, no deps) | `sdks/node` | Same as Python, for Node; `npx @foid/node keygen` |
| `@foid/react` | `sdks/react` | Browser: `<FoidProvider>`, `<ContinueWithFoid>`, `useFoidLogin()`, and a framework-free core (`@foid/react/core`) |

Guide: [`docs/continue-with-foid.md`](../../docs/continue-with-foid.md#developer-guide). Not published to PyPI/npm yet —
install from the repo (`pip install ./sdks/python`, `npm install ./sdks/node ./sdks/react`).

Rules: the client ID is the only FOID value that goes in a browser or mobile app. The client secret, private key and
API key stay on your server. Exchange each code once, within 60 seconds.
