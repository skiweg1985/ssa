import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true, // Erlaubt Zugriff von allen Netzwerk-Interfaces (0.0.0.0)
    port: 5173,
    proxy: {
      '/api': {
        // Muss zum lokalen Backend passen (uvicorn --port 8080, siehe
        // docs/README_SERVER.md); vorher stand hier faelschlich Port 80.
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
