import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  base: '/manual-synthesis/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // `base` applies in dev too, so API calls arrive prefixed like they do behind nginx.
      '/manual-synthesis/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/manual-synthesis/, ''),
      }
    }
  }
})
