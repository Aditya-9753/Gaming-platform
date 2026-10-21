import { useState } from 'react'

/**
 * Quick-bet chips the player can edit (pencil). Values are rupees and are
 * remembered per `storageKey` in this browser.
 */
export function useQuickAmounts(storageKey: string, defaults: number[]) {
  const read = (): number[] => {
    try {
      const raw = window.localStorage.getItem(storageKey)
      const parsed = raw ? (JSON.parse(raw) as unknown) : null
      if (Array.isArray(parsed) && parsed.length === defaults.length && parsed.every((n) => typeof n === 'number' && n > 0)) {
        return parsed as number[]
      }
    } catch { /* storage unavailable */ }
    return defaults
  }
  const [amounts, setAmounts] = useState<number[]>(read)
  const save = (next: number[]) => {
    setAmounts(next)
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)) } catch { /* ignore */ }
  }
  return { amounts, save, reset: () => save(defaults) }
}
