import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/links/': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      '/s/': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      '/users/': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
