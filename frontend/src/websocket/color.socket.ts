import { wsClient } from './websocket'
import { WS_EVENTS_V1 } from './events'
import { useGameStore } from '../store/game.store'
import type { GameRound } from '../types/game.types'

export const colorSocket = {
  subscribe: () => {
    wsClient.send(WS_EVENTS_V1.SUBSCRIBE, { channel: 'color' })

    const unsubRound = wsClient.on(WS_EVENTS_V1.COLOR_ROUND_START, (round: GameRound) => {
      useGameStore.getState().setCurrentRound('color', round)
    })

    const unsubResult = wsClient.on(WS_EVENTS_V1.COLOR_RESULT, (data: { roundId: string; winningColor: 'red' | 'green' | 'violet'; winningNumber: number }) => {
      const state = useGameStore.getState()
      const current = state.currentRound.color
      if (current && current.id === data.roundId) {
        const finished: GameRound = {
          ...current,
          status: 'ended',
          winningColor: data.winningColor,
          winningNumber: data.winningNumber,
        }
        state.setCurrentRound('color', finished)
        state.addRoundToHistory('color', finished)
      }
    })

    return () => {
      wsClient.send(WS_EVENTS_V1.UNSUBSCRIBE, { channel: 'color' })
      unsubRound()
      unsubResult()
    }
  },
}
