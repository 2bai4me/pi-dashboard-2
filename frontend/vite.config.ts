/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tailwind v4 Plugin deaktiviert: Sein Preflight überschreibt globale Styles
// (border: 0 solid, background-color: transparent, border-radius: 0) und
// zerstört damit alle expliziten Card/Button/Sidebar-Styles.
// Das Projekt nutzt keine Tailwind-Utilities, sondern reine CSS-Klassen
// aus index.css, daher ist das Plugin ueberfluessig.

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5181,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9220',
        changeOrigin: true,
        ws: false,
        secure: false,
        // 60s Timeout fuer Connection-Establishment (LLM-Validierung braucht lange)
        timeout: 60000,
        // 120s Timeout fuer Response (LLM-Validierung kann bis zu 30s dauern, plus Sicherheitspuffer)
        proxyTimeout: 120000,
        // Keep-Alive optimieren (User-Direktive 18.06.2026: Vite-Proxy-Saturation Fix)
        agent: false, // Node's default agent (Connection-Pooling)
        // Bypass-Funktion: SSE-Endpoints brauchen andere Settings
        bypass: (req: any, res: any) => {
          // SSE-Endpoint: Kein Timeout, kein Keep-Alive-Buffering
          if (req.url && req.url.includes('/api/kanban/events/')) {
            res.setHeader('Cache-Control', 'no-cache')
            res.setHeader('X-Accel-Buffering', 'no')
            return null // normaler Proxy-Modus
          }
          return null
        },
        // Error-Handler: Verhindert, dass Vite haengt bei Backend-Down
        onError: (err: any, req: any, res: any) => {
          console.error(`[vite-proxy] ${req.method} ${req.url} failed: ${err.code || err.message}`)
          if (res && !res.headersSent) {
            res.statusCode = 502
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({
              error: 'Backend-Proxy-Fehler',
              message: 'Backend auf Port 9220 nicht erreichbar oder Timeout',
              proxy: 'vite-dev-server',
              hint: 'Pruefe: läuft uvicorn? Port 9220 offen?',
            }))
          }
        },
        // Logging: nur Errors loggen (nicht jeden Request)
        logLevel: 'warn',
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    },
  },
})
