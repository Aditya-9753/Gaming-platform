import { useEffect, useRef, useState } from 'react'
import { WS_BASE_URL } from '../../../utils/constants'

export interface TeenPattiResult {
  roundId: string
  roundNo: number
  playerA: string[]
  playerB: string[]
  handA: string
  handB: string
  winner: 'A' | 'B' | 'TIE'
}

export type TeenPattiPhase = 'waiting' | 'betting' | 'locked' | 'result'

export interface TeenPattiRoundState {
  connected: boolean
  roundId: string | null
  roundNo: number
  phase: TeenPattiPhase
  /** Server-time epoch ms */
  lockAt: number
  secondsLeft: number
  payoutX100: number
  /** Live stake totals on each side this round (paise) */
  pool: { A: number; B: number; bets: number }
  result: TeenPattiResult | null
  /** Bumped when a round is settled (refresh wallet / history) */
  settledTick: number
}

interface Envelope {
  type?: string
  round_id?: string
  ts?: string
  data?: {
    status?: string
    round_id?: string
    round_no?: number
    betting_closes_at?: string
    payout_x100?: number
    metadata?: { betting_closes_at?: string; payout_x100?: number }
    player_a?: string[]
    player_b?: string[]
    hand_a?: string
    hand_b?: string
    winner?: 'A' | 'B' | 'TIE'
    bet_amount?: number
    side?: 'A' | 'B'
  }
}

const empty: TeenPattiRoundState = {
  connected: false, roundId: null, roundNo: 0, phase: 'waiting', lockAt: 0, secondsLeft: 0,
  payoutX100: 196, pool: { A: 0, B: 0, bets: 0 }, result: null, settledTick: 0,
}

export function useTeenPattiRound(): TeenPattiRoundState {
  const [state, setState] = useState<TeenPattiRoundState>(empty)
  const offset = useRef(0)

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout>
    let disposed = false

    const open = (event: Envelope, roundId: string | null | undefined, roundNo: number | undefined, closes?: string, payout?: number, locked = false) => {
      if (!closes || !roundId) return
      if (event.ts) offset.current = Date.parse(event.ts) - Date.now()
      const lockAt = Date.parse(closes)
      const now = Date.now() + offset.current
      setState((s) => ({
        ...s,
        roundId,
        roundNo: roundNo ?? s.roundNo,
        lockAt,
        secondsLeft: Math.max(0, Math.ceil((lockAt - now) / 1000)),
        phase: locked || now >= lockAt ? 'locked' : 'betting',
        payoutX100: payout ?? s.payoutX100,
        pool: s.roundId === roundId ? s.pool : { A: 0, B: 0, bets: 0 },
        result: null,
      }))
    }

    const connect = () => {
      if (disposed) return
      socket = new WebSocket(`${WS_BASE_URL.replace(/\/$/, '')}/games/teen_patti`)
      socket.onopen = () => setState((s) => ({ ...s, connected: true }))
      socket.onmessage = (message) => {
        let event: Envelope
        try { event = JSON.parse(message.data) as Envelope } catch { return }
        const d = event.data
        if (event.type === 'round_open') {
          open(event, event.round_id, d?.round_no, d?.betting_closes_at, d?.payout_x100)
        } else if (event.type === 'STATE_SNAPSHOT' && d?.metadata && (d.status === 'OPEN' || d.status === 'LOCKED')) {
          open(event, event.round_id ?? d.round_id, d.round_no, d.metadata.betting_closes_at, d.metadata.payout_x100, d.status === 'LOCKED')
        } else if (event.type === 'round_locked') {
          setState((s) => ({ ...s, phase: 'locked', secondsLeft: 0 }))
        } else if (event.type === 'bet_placed' && d?.side && typeof d.bet_amount === 'number') {
          const side = d.side
          const amount = d.bet_amount
          setState((s) => (event.round_id && event.round_id !== s.roundId ? s : {
            ...s,
            pool: { ...s.pool, [side]: s.pool[side] + amount, bets: s.pool.bets + 1 },
          }))
        } else if (event.type === 'result' && d?.player_a && d.player_b && d.winner && event.round_id) {
          const result: TeenPattiResult = {
            roundId: event.round_id,
            roundNo: d.round_no ?? 0,
            playerA: d.player_a,
            playerB: d.player_b,
            handA: d.hand_a ?? '',
            handB: d.hand_b ?? '',
            winner: d.winner,
          }
          setState((s) => ({ ...s, phase: 'result', result, secondsLeft: 0 }))
        } else if (event.type === 'round_settled') {
          setState((s) => ({ ...s, settledTick: s.settledTick + 1 }))
        }
      }
      socket.onclose = () => {
        if (disposed) return
        setState((s) => ({ ...s, connected: false }))
        reconnect = setTimeout(connect, 1500)
      }
      socket.onerror = () => socket?.close()
    }
    connect()

    const tick = setInterval(() => {
      const now = Date.now() + offset.current
      setState((s) => {
        if (s.phase !== 'betting') return s
        const secondsLeft = Math.max(0, Math.ceil((s.lockAt - now) / 1000))
        const phase: TeenPattiPhase = now >= s.lockAt ? 'locked' : 'betting'
        return secondsLeft === s.secondsLeft && phase === s.phase ? s : { ...s, secondsLeft, phase }
      })
    }, 200)

    return () => {
      disposed = true
      clearTimeout(reconnect)
      clearInterval(tick)
      socket?.close()
    }
  }, [])

  return state
}
