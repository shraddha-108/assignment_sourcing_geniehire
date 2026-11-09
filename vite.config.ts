import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: 'frontend',
  plugins: [react()],
  server: {
    watch: {
      ignored: ['**/recruiter-search-api/**'],
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
})