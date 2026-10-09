import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Never publish source maps: they would expose the original source code
    sourcemap: false,
  },
})
