import { create } from 'zustand'
import type { GameMetadata, GameRound, BetResult, GameId } from '../types/game.types'

interface GameState {
  gamesList: GameMetadata[]
  activeGameId: GameId | null
  currentRound: Partial<Record<GameId, GameRound>>
  roundHistory: Partial<Record<GameId, GameRound[]>>
  userActiveBets: BetResult[]
  wsConnected: boolean
  isReconnecting: boolean
  isMaintenance: boolean

  setGamesList: (games: GameMetadata[]) => void
  setActiveGame: (id: GameId | null) => void
  setCurrentRound: (gameId: GameId, round: GameRound) => void
  addRoundToHistory: (gameId: GameId, round: GameRound) => void
  addActiveBet: (bet: BetResult) => void
  removeActiveBet: (betId: string) => void
  setWsConnected: (v: boolean) => void
  setIsReconnecting: (v: boolean) => void
  setMaintenance: (v: boolean) => void
}

export const useGameStore = create<GameState>((set) => ({
  gamesList: [],
  activeGameId: null,
  currentRound: {},
  roundHistory: {},
  userActiveBets: [],
  wsConnected: false,
  isReconnecting: false,
  isMaintenance: false,

  setGamesList: (games) => set({ gamesList: games }),
  setActiveGame: (id) => set({ activeGameId: id }),

  setCurrentRound: (gameId, round) =>
    set((s) => ({ currentRound: { ...s.currentRound, [gameId]: round } })),

  addRoundToHistory: (gameId, round) =>
    set((s) => {
      const prev = s.roundHistory[gameId] || []
      return {
        roundHistory: {
          ...s.roundHistory,
          [gameId]: [round, ...prev].slice(0, 50),
        },
      }
    }),

  addActiveBet: (bet) =>
    set((s) => ({ userActiveBets: [...s.userActiveBets, bet] })),

  removeActiveBet: (betId) =>
    set((s) => ({
      userActiveBets: s.userActiveBets.filter((b) => b.id !== betId),
    })),

  setWsConnected: (v) => set({ wsConnected: v }),
  setIsReconnecting: (v) => set({ isReconnecting: v }),
  setMaintenance: (v) => set({ isMaintenance: v }),
}))
