# FOID Frontend

React SPA for the FOID Identity & Digital Risk Assessment platform.

## Stack

| Package | Purpose |
|---|---|
| **React 19** | UI framework |
| **TypeScript 6** | Type safety |
| **Vite 8** | Dev server and bundler |
| **Tailwind CSS 4** | Utility-first styling |
| **Framer Motion** | Page and component transitions |
| **React Router DOM v7** | Client-side routing |
| **Recharts** | Income/expense charts on the Reports page |
| **Axios** | HTTP client — wraps all API calls with auto token injection and silent refresh |
| **Remix Icon** | Icon set |

---

## Prerequisites

- [Node.js](https://nodejs.org/) ≥ 20
- [pnpm](https://pnpm.io/installation) ≥ 9

---

## Setup

```bash
cd frontend
pnpm install
pnpm dev
# → http://localhost:5173
```

The Vite dev server proxies all `/api/*` requests to `http://localhost:8000` — no hardcoded
localhost URLs in source code.

---

## Build

```bash
cd frontend
pnpm build        # tsc type-check + vite bundle → dist/
pnpm preview      # preview the production build locally
```

---

## Project Structure

```
frontend/src/
├── App.tsx                     Route declarations
├── main.tsx                    React root mount
├── index.css                   Global base styles
│
├── lib/
│   └── api.ts                  Axios client — access token in memory, refresh token
│                               in localStorage under key "idra_refresh_token"
│
├── types/
│   └── foid.ts                 TypeScript interfaces (User, Credential, etc.)
│
├── contexts/
│   ├── AuthContext.tsx          Auth state, login/signup/logout, refreshUser()
│   └── CredentialContext.tsx    Credential state machine (client-side mirror)
│
├── layouts/
│   └── DashboardLayout.tsx      Sidebar + topbar shell for all dashboard pages
│
├── components/
│   ├── Sidebar.tsx
│   ├── Topbar.tsx
│   ├── AiChat.tsx              Floating AI chat widget
│   ├── IncomeExpenseChart.tsx
│   ├── StatCard.tsx
│   ├── ProtectedRoute.tsx      Redirects unauthenticated users to /login
│   └── landing/               Landing page nav + footer
│
└── pages/
    ├── LandingPage.tsx         Public marketing page
    ├── auth/
    │   ├── LoginPage.tsx
    │   └── SignupPage.tsx
    └── dashboard/
        ├── OverviewPage.tsx             Summary stats + quick actions
        ├── MyIdentityPage.tsx           BVN / phone / liveness verification
        ├── VerificationCredentialsPage  Credential state + claims
        ├── ProfileSettingsPage.tsx      Name, address, avatar, password
        ├── ConnectedBankPage.tsx        Mono bank linking
        ├── BusinessLedgerPage.tsx       Receipt upload + manual entry
        ├── LedgerHistoryPage.tsx        Ledger table with filters
        ├── ReportsPage.tsx              Monthly charts and PDF export
        ├── AICreditWalletPage.tsx       Balance, transactions, top-up
        └── ConsentPage.tsx             Platform consent management
```

---

## Auth Architecture

- **Access token** — stored in a module-level variable inside `lib/api.ts` (never `localStorage` or `sessionStorage`). Survives the tab session, lost on tab close.
- **Refresh token** — stored in `localStorage` under key `idra_refresh_token`.
- **Session restore** — on app mount, `AuthContext` calls `POST /api/v1/auth/refresh` using the stored refresh token, then `GET /api/v1/auth/me` to populate user state.
- **Silent refresh** — Axios response interceptor catches `401` errors, refreshes the access token automatically, and retries the original request.
- **`loading` state** — `AuthContext` exposes `loading: boolean` that is `true` until the session restore completes, preventing flash-of-unauthenticated-content.

---

## API Client

All requests go through the singleton Axios instance at [`lib/api.ts`](src/lib/api.ts):

```ts
import api from '@/lib/api'

// Authenticated request (token injected automatically)
const { data } = await api.get('/api/v1/credentials/me')

// Public request
const { data } = await api.post('/api/v1/auth/login', { email, password })
```

---

## Environment

No `.env` file is needed for the frontend in development — the Vite proxy forwards `/api/*`
to the backend. For production builds, set the backend origin in `vite.config.ts`.

---

## TypeScript Notes

- `verbatimModuleSyntax: true` — use `import type { Foo }` for type-only imports
- `noUnusedLocals` and `noUnusedParameters` are enabled — every declared symbol must be used
- Path alias `@/` resolves to `src/`

Run the type-checker:

```bash
pnpm build    # tsc + vite (full type-check gate)
```
