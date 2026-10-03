export type GameId = 'aviator' | 'color' | 'mines' | 'cricket'

export type GameStatus = 'idle' | 'betting' | 'running' | 'crashed' | 'ended' | 'maintenance'

export interface GameMetadata {
  id: GameId
  name: string
  description: string
  thumbnailUrl: string
  isActive: boolean
  minBetPaise: number
  maxBetPaise: number
  houseEdgePercent: number
  rtpPercent: number
  currentPlayersCount: number
  /** Shown in the lobby but not playable yet */
  comingSoon?: boolean
}

export interface ProvablyFairData {
  roundId: string
  serverSeedHash: string
  clientSeed: string
  nonce: number
  serverSeed?: string // Revealed after round ends
  finalResult?: string | number
  verified?: boolean
}

export interface GameRound {
  id: string
  gameId: GameId
  status: GameStatus
  roundNumber: number
  startTime: number // ms timestamp
  bettingEndTime?: number
  crashMultiplier?: number // Aviator
  winningColor?: 'red' | 'green' | 'violet' // Color prediction
  winningNumber?: number // Color prediction
  provablyFair: ProvablyFairData
}

export interface BetRequest {
  gameId: GameId
  roundId: string
  amountPaise: number
  prediction?: string | number | Record<string, unknown>
  autoCashoutMultiplier?: number
  idempotencyKey: string
}

export interface BetResult {
  id: string
  roundId: string
  gameId: GameId
  userId: string
  betAmountPaise: number
  cashoutMultiplier?: number
  payoutAmountPaise: number
  isWon: boolean
  status: 'active' | 'cashed_out' | 'lost' | 'refunded'
  createdAt: string
}
