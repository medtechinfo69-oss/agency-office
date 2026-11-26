import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Both dev and the production preview proxy /api, /ws and /media to the
// FastAPI backend, so the browser only ever talks to one origin (works
// behind the Arena preview proxy too).
const backend = process.env.API_PROXY_TARGET || 'http://localhost:8000'
const proxy = {
  '/api': { target: backend, changeOrigin: true },
  '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
  '/media': { target: backend, changeOrigin: true },
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy,
  },
  // production preview (npm run preview) — serves dist/ with the same proxy
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy,
  },
})
