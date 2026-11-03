import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker the backend serves the built app, so this is only for `npm run dev`.
// DEMO_BACKEND picks which server the dev UI talks to (Python 3100 or Node 3200).
const backend = process.env.DEMO_BACKEND || 'http://127.0.0.1:3100'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5300,
    strictPort: true,
    proxy: { '/api': backend, '/webhooks': backend },
  },
})
