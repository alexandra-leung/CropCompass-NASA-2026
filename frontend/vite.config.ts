import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Keep browser requests on the same origin in development and preview.
// Vite forwards /api/... to the hosted FastAPI backend.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.VITE_BACKEND_URL || env.VITE_API_URL || 'https://cropcompass-api-i27c.onrender.com'
  return {
    plugins: [react()],
    server: { host: true, proxy: { '/api': { target: backend, changeOrigin: true } } },
    preview: { host: true, proxy: { '/api': { target: backend, changeOrigin: true } } },
  }
})
