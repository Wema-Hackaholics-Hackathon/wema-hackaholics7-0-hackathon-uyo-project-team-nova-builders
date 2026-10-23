import { defineConfig , loadEnv} from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'



export default defineConfig(({ mode }) => {
  // Load env variables
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      tailwindcss(),
      react(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000', // fallback
          changeOrigin: true,
        },
      },
    },
  }
})