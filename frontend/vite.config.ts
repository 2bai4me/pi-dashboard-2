import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5181,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9220',
        changeOrigin: true,
      },
    },
  },
})
