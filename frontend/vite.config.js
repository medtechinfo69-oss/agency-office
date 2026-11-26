import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Both dev and the production preview proxy /api, /ws and /media to the
// FastAPI backend, so the browser only ever talks to one origin (works
// behind the Arena preview proxy too).
const proxy = {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
  '/ws': { target: 'ws://localhost:8000', ws: true },
  '/media': { target: 'http://localhost:8000', changeOrigin: true },
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
