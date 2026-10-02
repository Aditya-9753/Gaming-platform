import { wsClient } from './websocket'
import { WS_EVENTS_V1 } from './events'
import { useGameStore } from '../store/game.store'
import type { GameRound } from '../types/game.types'

export const aviatorSocket = {
  subscribe: () => {
    wsClient.send(WS_EVENTS_V1.SUBSCRIBE, { channel: 'aviator' })

    const unsubRound = wsClient.on(WS_EVENTS_V1.AVIATOR_ROUND_START, (round: GameRound) => {
      useGameStore.getState().setCurrentRound('aviator', round)
    })

    const unsubCrash = wsClient.on(WS_EVENTS_V1.AVIATOR_CRASH, (data: { roundId: string; multiplier: number }) => {
      const state = useGameStore.getState()
      const current = state.currentRound.aviator
      if (current && current.id === data.roundId) {
        const finished: GameRound = {
          ...current,
          status: 'crashed',
          crashMultiplier: data.multiplier,
        }
        state.setCurrentRound('aviator', finished)
        state.addRoundToHistory('aviator', finished)
      }
    })

    return () => {
      wsClient.send(WS_EVENTS_V1.UNSUBSCRIBE, { channel: 'aviator' })
      unsubRound()
      unsubCrash()
    }
  },
}
