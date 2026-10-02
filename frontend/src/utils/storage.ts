/**
 * LocalStorage wrapper strictly for UI preferences and non-sensitive cache.
 * SECURITY NOTICE: NEVER store JWTs, access tokens, or refresh tokens in localStorage.
 * Auth tokens are held in-memory and refreshed via httpOnly cookies.
 */

export const storage = {
  get<T>(key: string, defaultValue: T): T {
    try {
      const item = localStorage.getItem(key)
      if (item === null) return defaultValue
      return JSON.parse(item) as T
    } catch {
      return defaultValue
    }
  },

  set<T>(key: string, value: T): void {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch (e) {
      console.warn(`Failed to store key "${key}" in localStorage:`, e)
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(key)
    } catch (e) {
      console.warn(`Failed to remove key "${key}" from localStorage:`, e)
    }
  },

  clear(): void {
    try {
      localStorage.clear()
    } catch (e) {
      console.warn('Failed to clear localStorage:', e)
    }
  },
}
