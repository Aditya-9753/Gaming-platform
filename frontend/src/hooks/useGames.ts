import { useCallback } from 'react'
import { useGameStore } from '../store/game.store'
import { gameApi } from '../services/game.api'
import { showToast } from '../components/common/Toast'

export function useGames() {
  const { gamesList, currentRound, setGamesList, setCurrentRound } = useGameStore()

  const fetchGames = useCallback(async () => {
    try {
      const games = await gameApi.getGames()
      setGamesList(games)
    } catch {
      showToast({ title: 'Games unavailable', message: 'Could not load the game catalog from the server.', type: 'error' })
    }
  }, [setGamesList])

  const fetchCurrentRound = useCallback(async (gameId: string) => {
    try {
      const round = await gameApi.getCurrentRound(gameId)
      setCurrentRound(gameId as Parameters<typeof setCurrentRound>[0], round)
      return round
    } catch {
      showToast({ title: 'Round unavailable', message: `Could not load the current ${gameId} round.`, type: 'warning' })
      return null
    }
  }, [setCurrentRound])

  return { gamesList, currentRound, fetchGames, fetchCurrentRound }
}
