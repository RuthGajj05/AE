import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen beyond localhost and accept Cloudflare quick-tunnel hostnames so teammates can open the dev server.
    host: true,
    allowedHosts: ['.trycloudflare.com'],
    // Same-origin backend: the browser calls /api, Vite forwards it to the backend on this machine.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
