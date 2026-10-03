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
