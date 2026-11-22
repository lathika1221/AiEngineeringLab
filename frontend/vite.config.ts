import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * A production build must be told where the API lives. Without this check the
 * bundle would silently call http://127.0.0.1:8000 (see src/shared/api/client.ts).
 * The value is never echoed in the error message.
 */
function assertProductionApiUrl(raw: string | undefined): void {
  const value = (raw ?? '').trim()
  if (!value) {
    throw new Error('VITE_API_URL must be set for a production build (for example https://your-api.onrender.com).')
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_API_URL is not a valid URL.')
  }

  const host = url.hostname.toLowerCase()
  const isLocal =
    host === 'localhost' || host.endsWith('.localhost') || host === '0.0.0.0' || host === '[::1]' || /^127\./.test(host)

  if (url.protocol !== 'https:') {
    throw new Error('VITE_API_URL must use https:// in a production build.')
  }
  if (isLocal) {
    throw new Error('VITE_API_URL must not point at localhost in a production build.')
  }
  if (url.username || url.password || url.search || url.hash || url.pathname.replace(/\/+$/, '') !== '') {
    throw new Error('VITE_API_URL must be an origin only (scheme, host and optional port), with no credentials, path, query or fragment.')
  }
}

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  if (command === 'build' && mode === 'production') {
    assertProductionApiUrl(loadEnv(mode, '.', 'VITE_').VITE_API_URL)
  }

  return {
    plugins: [react()],
  }
})
