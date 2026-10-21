import axios from 'axios'

/** Site key from a CAPTCHA_REQUIRED sign-in error, else null. */
export const captchaSiteKey = (error: unknown): string | null => {
  if (!axios.isAxiosError(error)) return null
  const body = error.response?.data as { error?: { code?: string; details?: { site_key?: string } } } | undefined
  return body?.error?.code === 'CAPTCHA_REQUIRED' ? body.error.details?.site_key || null : null
}
