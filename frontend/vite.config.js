import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

// The dev server is reachable through the tunnel and the local network, and /api is proxied to the backend on this
// laptop, so a shared link would also hand out the backend (and the API spend behind it). /api only answers requests
// made on this laptop unless the dev server is started with SHARE_API=1. Shared pages fall back to sample data.
function localOnlyApi() {
  return {
    name: 'local-only-api',
    configureServer(server) {
      // Added before Vite's own middlewares, so this runs ahead of the /api proxy.
      server.middlewares.use('/api', (req, res, next) => {
        let hostname = ''
        try {
          hostname = new URL(`http://${req.headers.host ?? ''}`).hostname
        } catch {
          // Unparseable Host header: treat it as not local.
        }
        if (process.env.SHARE_API === '1' || LOCAL_HOSTS.has(hostname)) return next()
        res.statusCode = 403
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ error: 'The backend is only reachable on this laptop. Start the dev server with SHARE_API=1 to share it.' }))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), localOnlyApi()],
  server: {
    // Listen beyond localhost and accept Cloudflare quick-tunnel hostnames so teammates can open the dev server.
    host: true,
    allowedHosts: ['.trycloudflare.com'],
    // Same-origin backend: the browser calls /api, Vite forwards it to the backend on this machine.
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    rollupOptions: {
      // crumbs is the main app; the LocalEdge dashboard lives at /localedge.html
      input: { main: 'index.html', localedge: 'localedge.html' },
    },
  },
})
