import { useEffect, useState } from 'react'
import { apiClient } from '../services/api'

type Counts = Record<string, number>

// One shared poll for every lobby tile on the page (real players only — see backend live_players.py)
const POLL_MS = 20_000
let counts: Counts = {}
let timer: number | undefined
const listeners = new Set<(c: Counts) => void>()

async function refresh() {
  try {
    const { data } = await apiClient.get<{ games: Counts }>('/games/live/players')
    counts = data.games
    listeners.forEach((fn) => fn(counts))
  } catch { /* keep the last known numbers */ }
}

// Staff-only preview numbers so admins can see how busy tiles look while testing.
// Never shown to players: they always get the real counts above.
const DEMO_BASE: Record<string, number> = { aviator: 1840, color: 2630, mines: 940, teen_patti: 1210 }

export function demoPlayers(gameId: string, now = Date.now()): number {
  const base = DEMO_BASE[gameId] ?? 500
  const minutes = now / 60_000
  const seed = [...gameId].reduce((a, c) => a + c.charCodeAt(0), 0)
  const daily = Math.sin((minutes / 1440) * Math.PI * 2 + seed) * 0.25 // slow rise and fall over the day
  const wave = Math.sin(minutes / 7 + seed) * 0.06                     // a few minutes of drift
  const bucket = Math.floor(now / POLL_MS)
  const jitter = (((bucket * 9301 + seed * 49297) % 233280) / 233280 - 0.5) * 0.04
  return Math.max(12, Math.round(base * (1 + daily + wave + jitter)))
}

/** Real players active in each lobby game over the last few minutes. */
export function useLivePlayers(): Counts {
  const [value, setValue] = useState<Counts>(counts)
  useEffect(() => {
    listeners.add(setValue)
    if (listeners.size === 1) {
      void refresh()
      timer = window.setInterval(() => { void refresh() }, POLL_MS)
    }
    return () => {
      listeners.delete(setValue)
      if (listeners.size === 0 && timer) { window.clearInterval(timer); timer = undefined }
    }
  }, [])
  return value
}
