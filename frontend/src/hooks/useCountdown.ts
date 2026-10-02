import { useState, useEffect, useRef } from 'react'

export function useCountdown(targetMs: number): number {
  const [remaining, setRemaining] = useState(Math.max(0, targetMs - Date.now()))
  const rafRef = useRef<number>(0)

  useEffect(() => {
    const tick = () => {
      const r = Math.max(0, targetMs - Date.now())
      setRemaining(r)
      if (r > 0) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [targetMs])

  return remaining
}

