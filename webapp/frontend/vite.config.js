import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/item-images': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/item-uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/item-originals': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
