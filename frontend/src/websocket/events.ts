/**
 * Versioned WebSocket Event Schemas (v1)
 */
export const WS_EVENTS_V1 = {
  // Client -> Server
  AUTH_TICKET: 'v1.client.auth',
  PING: 'v1.client.ping',
  SUBSCRIBE: 'v1.client.subscribe',
  UNSUBSCRIBE: 'v1.client.unsubscribe',

  // Server -> Client
  PONG: 'v1.server.pong',
  ERROR: 'v1.server.error',
  MAINTENANCE: 'v1.server.maintenance',

  // Aviator
  AVIATOR_ROUND_START: 'v1.aviator.round_start',
  AVIATOR_TICK: 'v1.aviator.tick',
  AVIATOR_CRASH: 'v1.aviator.crash',
  AVIATOR_BET_PLACED: 'v1.aviator.bet_placed',
  AVIATOR_CASHOUT: 'v1.aviator.cashout',

  // Color Prediction
  COLOR_ROUND_START: 'v1.color.round_start',
  COLOR_COUNTDOWN: 'v1.color.countdown',
  COLOR_RESULT: 'v1.color.result',

  // Global Notifications
  NOTIFICATION_NEW: 'v1.notification.new',
  WALLET_BALANCE_UPDATED: 'v1.wallet.updated',
} as const

export interface WsMessage<T = unknown> {
  event: string
  payload: T
  timestamp: number
  serverTime?: number
}
