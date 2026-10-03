import { apiClient } from './api'
import type { GameMetadata, GameRound, BetRequest, BetResult } from '../types/game.types'

/** Games that are listed in the lobby but not open for play yet. */
export const COMING_SOON_GAMES = new Set(['cricket'])
const LOBBY_ORDER = ['aviator', 'color', 'mines', 'cricket']
const lobbyRank = (id: string) => {
  const i = LOBBY_ORDER.indexOf(id)
  return i === -1 ? LOBBY_ORDER.length : i
}

interface ApiGame {
  id: string
  name: string
  description?: string | null
  is_active: boolean
  min_bet: number
  max_bet: number
  house_edge_percent: number
}

export const gameApi = {
  getGames: async (): Promise<GameMetadata[]> => {
    const { data } = await apiClient.get<ApiGame[]>('/games')
    // WinGo modes (wingo_30s ...) live inside the single Color Prediction card
    return data
      .filter((game) => !game.id.startsWith('wingo_'))
      .sort((a, b) => lobbyRank(a.id) - lobbyRank(b.id))
      .map((game) => ({
      id: game.id as GameMetadata['id'],
      name: game.name,
      description: game.description || '',
      thumbnailUrl: game.id === 'aviator' ? '/games/aviator/cover.jpg' : `/games/${game.id}.png`,
      isActive: game.is_active,
      minBetPaise: game.min_bet,
      maxBetPaise: game.max_bet,
      houseEdgePercent: game.house_edge_percent,
      rtpPercent: 100 - game.house_edge_percent,
      currentPlayersCount: 0,
      comingSoon: COMING_SOON_GAMES.has(game.id),
    }))
  },

  getCurrentRound: async (gameId: string): Promise<GameRound> => {
    const { data } = await apiClient.get<{ active: boolean; round_id?: string; round_no?: number; status?: string; started_at?: string | null; server_seed_hash?: string }>(`/games/${gameId}/round`)
    if (!data.active || !data.round_id) throw new Error('No active round')
    return {
      id: data.round_id,
      gameId: gameId as GameRound['gameId'],
      status: (data.status?.toLowerCase() || 'betting') as GameRound['status'],
      roundNumber: data.round_no || 0,
      startTime: data.started_at ? Date.parse(data.started_at) : 0,
      provablyFair: { roundId: data.round_id, serverSeedHash: data.server_seed_hash || '', clientSeed: '', nonce: 0 },
    }
  },

  placeBet: async (gameId: string, payload: BetRequest, idempotencyKey: string): Promise<BetResult> => {
    const { data } = await apiClient.post<BetResult>(
      `/games/${gameId}/action`,
      {
        action: 'bet',
        round_id: payload.roundId,
        amount: payload.amountPaise,
        auto_cashout: payload.autoCashoutMultiplier,
      },
      { headers: { 'Idempotency-Key': idempotencyKey } }
    )
    return data
  },

  cashoutAviator: async (roundId: string, entryId: string, idempotencyKey: string): Promise<BetResult> => {
    const { data } = await apiClient.post<BetResult>(
      '/games/aviator/action',
      { action: 'cashout', round_id: roundId, entry_id: entryId },
      { headers: { 'Idempotency-Key': idempotencyKey } }
    )
    return data
  },

  getRoundHistory: async (gameId: string, limit = 20): Promise<GameRound[]> => {
    const { data } = await apiClient.get<{ items: Array<Record<string, unknown>> }>(`/games/${gameId}/rounds`, { params: { page_size: limit } })
    return data.items as unknown as GameRound[]
  },

  getUserBetHistory: async (gameId?: string, page = 1): Promise<{ items: BetResult[]; total: number }> => {
    const { data } = await apiClient.get('/users/me/history', { params: { game_id: gameId, page, page_size: 20 } })
    return data
  },
}
