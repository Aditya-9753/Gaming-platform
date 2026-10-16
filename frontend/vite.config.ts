import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

/**
 * Opens the connection to the API server while the page is still loading (DNS + TLS
 * handshake), so the first API call does not pay for it. The origin comes from
 * VITE_API_BASE_URL, which Vercel provides at build time.
 */
function preconnectApi(apiBase: string | undefined): Plugin {
  return {
    name: 'preconnect-api',
    transformIndexHtml() {
      if (!apiBase) return []
      let origin: string
      try { origin = new URL(apiBase).origin } catch { return [] }
      return [
        { tag: 'link', attrs: { rel: 'preconnect', href: origin, crossorigin: '' }, injectTo: 'head-prepend' },
        { tag: 'link', attrs: { rel: 'dns-prefetch', href: origin }, injectTo: 'head-prepend' },
      ]
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react(), preconnectApi(process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL)],
    build: {
      // Never publish source maps: they would expose the original source code
      sourcemap: false,
    },
  }
})
