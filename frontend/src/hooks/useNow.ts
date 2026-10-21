import { useEffect, useState } from 'react'

/**
 * Current time in ms, refreshed every `intervalMs`. Lets render code compare
 * against "now" without calling Date.now() during render.
 */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}
