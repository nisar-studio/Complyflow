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
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    css: false,
    moduleNameMapper: {
      '^lucide-react$': '<rootDir>/src/test/__mocks__/lucide-react.jsx',
    },
    coverage: {
      provider: 'v8',
    },
  },
})
