import axios from 'axios'

/** Extract the backend's `{ error: { message } }` text, falling back to a friendly default. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback
  if (!error.response) return 'Cannot reach the game server. Check that the backend is running.'
  const body = error.response.data as {
    error?: { message?: string; details?: Array<{ msg?: string }> }
    detail?: string
  } | undefined
  const detail = body?.error?.details?.[0]?.msg?.replace(/^Value error,\s*/i, '')
  return detail || body?.error?.message || body?.detail || fallback
}
