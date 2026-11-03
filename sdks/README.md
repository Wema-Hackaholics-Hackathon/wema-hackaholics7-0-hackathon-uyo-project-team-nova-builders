# FOID SDKs

Official SDKs for [FOID](../README.md): verify once, share with consent.

| Package | Folder | Runs on | Use it for |
|---|---|---|---|
| [`foid`](python/) | `sdks/python` | Your server: Python ≥ 3.10 | Continue with FOID code exchange, the Open API, webhook signatures, key pairs |
| [`@foid/node`](node/) | `sdks/node` | Your server: Node ≥ 18, no dependencies | The same, for Node |
| [`@foid/react`](react/) | `sdks/react` | The browser | The "Continue with FOID" button, hook and popup |

A typical integration uses two: the React button in your front end, and a server SDK in the endpoint that receives the one-time code.

```
<ContinueWithFoid>  ── code + codeVerifier ──▶  your server: foid.oauth.exchange()  ──▶  FOID
   (client ID only)                                (client secret or private key)
```

## Install

Not on PyPI or npm yet. Install from this folder:

```bash
pip install "./sdks/python[keypair]"
npm install ./sdks/node
npm install ./sdks/react
```

Or pack them and depend on the files, as `demo/` does (`uv build --wheel`, `npm pack`).

## Rules that apply to all of them

- The **client ID** is the only FOID value that goes in a browser or mobile app.
- The **API key**, **client secret** and **private key** stay on your server.
- Exchange each sign-in code **once**, on your server, within **60 seconds**. A reused code revokes the grant.
- Verify every webhook against the **raw** request body.

## Docs

The full documentation is in [`docs/`](../docs). Run it with `cd docs && pnpm dev`, then open http://localhost:5177:

- SDK reference: `/sdks/python`, `/sdks/node`, `/sdks/react`
- Guide: `/guide/continue-with-foid`
- A live button to try: `/playground`
- A complete example app using all three: [`demo/`](../demo) (`/sdks/example-app`)
