import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The API runs on :8000 (`make dev-backend`). Proxying /api keeps the app same-origin in
// development, so no CORS is involved. 127.0.0.1, not localhost: uvicorn listens on IPv4
// only, and Node may resolve localhost to ::1 first.
const API_TARGET = process.env.PITCHQUERY_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
