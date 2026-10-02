import { useEffect, useState } from 'react'
import { WS_BASE_URL } from '../../../utils/constants'

type Phase = 'waiting' | 'betting' | 'flying' | 'crashed'

export interface AviatorCashoutEvent {
  entryId: string
  multiplier: number
  payout: number
  automatic: boolean
  /** Monotonic counter so identical consecutive events still trigger effects. */
  seq: number
}

export interface AviatorLiveBet {
  entryId: string
  player: string
  amount: number
  autoCashout?: number | null
  cashedAt?: number
  payout?: number
}

export interface AviatorState {
  phase: Phase
  multiplier: number
  roundNumber: number
  roundId: string | null
  countdown: number
  /** Length of the betting window in seconds (for the progress bar). */
  bettingTotal: number
  serverSeedHash: string
  lastCashout: AviatorCashoutEvent | null
  connected: boolean
  /** Live feed of every (masked) player's bet in the current round. */
  bets: AviatorLiveBet[]
}

interface GrowthParameters { rate: number; power: number; model?: 'exponential' | 'power' }

/** Same curve the server uses (app/games/aviator/rules.py). */
const multiplierAt = (elapsed: number, g: GrowthParameters) =>
  g.model === 'exponential' ? Math.exp(g.rate * elapsed) : 1 + (elapsed * g.rate) ** g.power

interface GameEvent {
  type?: string
  data?: {
    round_no?: number
    round_start_ts?: string
    growth_parameters?: GrowthParameters
    crash_point?: number
    server_seed_hash?: string
    // cashout
    entry_id?: string
    player?: string
    bet_amount?: number
    auto_cashout?: number | null
    multiplier?: number
    payout?: number
    automatic?: boolean
    // STATE_SNAPSHOT
    round_id?: string
    status?: string
    metadata?: { round_start_ts?: string; growth_parameters?: GrowthParameters }
  }
  ts?: string
  round_id?: string
}

const initialState: AviatorState = {
  phase: 'waiting',
  multiplier: 1,
  roundNumber: 0,
  roundId: null,
  countdown: 0,
  bettingTotal: 6,
  serverSeedHash: '',
  lastCashout: null,
  connected: false,
  bets: [],
}

export function useAviatorRound() {
  const [state, setState] = useState(initialState)

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout>
    let disposed = false
    let startAt = 0
    let serverOffset = 0
    let growth: GrowthParameters | null = null
    let cashoutSeq = 0

    const serverNow = () => Date.now() + serverOffset

    const beginRound = (event: GameEvent, roundStartTs: string, parameters: GrowthParameters, roundNo?: number, seedHash?: string) => {
      startAt = Date.parse(roundStartTs)
      if (event.ts) serverOffset = Date.parse(event.ts) - Date.now()
      growth = parameters
      const remaining = Math.max(0, (startAt - serverNow()) / 1000)
      setState((previous) => ({
        ...initialState,
        phase: remaining > 0 ? 'betting' : 'flying',
        roundNumber: roundNo ?? previous.roundNumber,
        roundId: event.round_id ?? event.data?.round_id ?? null,
        countdown: Math.ceil(remaining),
        bettingTotal: Math.max(Math.ceil(remaining), 1),
        serverSeedHash: seedHash ?? '',
        lastCashout: previous.lastCashout,
        connected: true,
      }))
    }

    const connect = () => {
      if (disposed) return
      socket = new WebSocket(`${WS_BASE_URL.replace(/\/$/, '')}/games/aviator`)
      socket.onopen = () => setState((previous) => ({ ...previous, connected: true }))
      socket.onmessage = (message) => {
        let event: GameEvent
        try {
          event = JSON.parse(message.data) as GameEvent
        } catch {
          return
        }
        const data = event.data
        switch (event.type) {
          case 'round_open':
            if (data?.round_start_ts && data.growth_parameters) {
              beginRound(event, data.round_start_ts, data.growth_parameters, data.round_no, data.server_seed_hash)
            }
            break
          case 'STATE_SNAPSHOT': {
            // Joined mid-round: resume betting countdown or the live flight.
            const meta = data?.metadata
            const status = data?.status
            if (meta?.round_start_ts && meta.growth_parameters && (status === 'BETTING_OPEN' || status === 'RUNNING')) {
              beginRound(event, meta.round_start_ts, meta.growth_parameters, data?.round_no, data?.server_seed_hash)
            }
            break
          }
          case 'crash':
            setState((previous) => ({
              ...previous,
              phase: 'crashed',
              countdown: 0,
              multiplier: data?.crash_point ?? previous.multiplier,
            }))
            break
          case 'bet_placed':
            if (data?.entry_id) {
              const bet: AviatorLiveBet = {
                entryId: data.entry_id,
                player: data.player ?? '***',
                amount: data.bet_amount ?? 0,
                autoCashout: data.auto_cashout,
              }
              setState((previous) => previous.bets.some((b) => b.entryId === bet.entryId)
                ? previous
                : { ...previous, bets: [bet, ...previous.bets].slice(0, 200) })
            }
            break
          case 'cashout':
            if (data?.entry_id && typeof data.multiplier === 'number') {
              const { entry_id: cashedId, multiplier: cashedAt, payout } = data
              setState((previous) => ({
                ...previous,
                bets: previous.bets.map((b) => (b.entryId === cashedId ? { ...b, cashedAt, payout } : b)),
              }))
              cashoutSeq += 1
              const cashout: AviatorCashoutEvent = {
                entryId: data.entry_id,
                multiplier: data.multiplier,
                payout: data.payout ?? 0,
                automatic: Boolean(data.automatic),
                seq: cashoutSeq,
              }
              setState((previous) => ({ ...previous, lastCashout: cashout }))
            }
            break
          default:
            break
        }
      }
      socket.onclose = () => {
        if (!disposed) setState((previous) => ({ ...previous, connected: false }))
        if (!disposed) reconnectTimer = setTimeout(connect, 1500)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    const animationTimer = setInterval(() => {
      const now = serverNow()
      setState((previous) => {
        if (previous.phase === 'betting') {
          const countdown = Math.max(0, Math.ceil((startAt - now) / 1000))
          if (now >= startAt && growth) {
            return { ...previous, phase: 'flying', countdown: 0, multiplier: 1 }
          }
          return countdown === previous.countdown ? previous : { ...previous, countdown }
        }
        if (previous.phase === 'flying') {
          const elapsed = Math.max(0, (now - startAt) / 1000)
          return growth ? { ...previous, multiplier: multiplierAt(elapsed, growth) } : previous
        }
        return previous
      })
    }, 50)

    return () => {
      disposed = true
      clearInterval(animationTimer)
      clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return state
}
