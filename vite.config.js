import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
