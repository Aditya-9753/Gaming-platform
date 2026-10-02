import { useEffect, useRef, useState } from 'react'
import { WS_BASE_URL } from '../../../utils/constants'

export interface WingoResult {
  roundId: string
  period: string
  number: number
  colours: string[]
  size: string
  payoutsX100?: Record<string, number>
}

export interface WingoRoundState {
  connected: boolean
  roundId: string | null
  period: string
  /** Server-time epoch ms */
  lockAt: number
  resultAt: number
  secondsLeft: number
  locked: boolean
  lastResult: WingoResult | null
}

interface Envelope {
  type?: string
  round_id?: string
  ts?: string
  data?: {
    period?: string
    betting_closes_at?: string
    result_at?: string
    status?: string
    round_id?: string
    number?: number
    colours?: string[]
    size?: string
    payouts_x100?: Record<string, number>
    metadata?: { period?: string; betting_closes_at?: string; result_at?: string }
  }
}

const empty: WingoRoundState = {
  connected: false, roundId: null, period: '', lockAt: 0, resultAt: 0, secondsLeft: 0, locked: true, lastResult: null,
}

export function useWingoRound(gameId: string): WingoRoundState {
  const [state, setState] = useState<WingoRoundState>(empty)
  const offsetRef = useRef(0)

  useEffect(() => {
    setState(empty)
    let socket: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout>
    let disposed = false

    const open = (event: Envelope, period?: string, closes?: string, result?: string, roundId?: string | null) => {
      if (!closes || !result) return
      if (event.ts) offsetRef.current = Date.parse(event.ts) - Date.now()
      const lockAt = Date.parse(closes)
      const resultAt = Date.parse(result)
      const now = Date.now() + offsetRef.current
      setState((s) => ({
        ...s,
        roundId: roundId ?? null,
        period: period ?? '',
        lockAt,
        resultAt,
        secondsLeft: Math.max(0, Math.ceil((resultAt - now) / 1000)),
        locked: now >= lockAt,
      }))
    }

    const connect = () => {
      if (disposed) return
      socket = new WebSocket(`${WS_BASE_URL.replace(/\/$/, '')}/games/${gameId}`)
      socket.onopen = () => setState((s) => ({ ...s, connected: true }))
      socket.onmessage = (message) => {
        let event: Envelope
        try { event = JSON.parse(message.data) as Envelope } catch { return }
        const d = event.data
        if (event.type === 'round_open') {
          open(event, d?.period, d?.betting_closes_at, d?.result_at, event.round_id)
        } else if (event.type === 'STATE_SNAPSHOT' && d?.metadata && (d.status === 'OPEN' || d.status === 'LOCKED')) {
          open(event, d.metadata.period, d.metadata.betting_closes_at, d.metadata.result_at, event.round_id ?? d.round_id)
        } else if (event.type === 'round_locked') {
          setState((s) => ({ ...s, locked: true }))
        } else if (event.type === 'result' && typeof d?.number === 'number' && event.round_id) {
          const result: WingoResult = {
            roundId: event.round_id,
            period: d.period ?? '',
            number: d.number,
            colours: d.colours ?? [],
            size: d.size ?? '',
            payoutsX100: d.payouts_x100,
          }
          setState((s) => ({ ...s, locked: true, lastResult: result }))
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
      const now = Date.now() + offsetRef.current
      setState((s) => {
        if (!s.resultAt) return s
        const secondsLeft = Math.max(0, Math.ceil((s.resultAt - now) / 1000))
        const locked = s.locked || now >= s.lockAt
        return secondsLeft === s.secondsLeft && locked === s.locked ? s : { ...s, secondsLeft, locked }
      })
    }, 200)

    return () => {
      disposed = true
      clearInterval(tick)
      clearTimeout(reconnect)
      socket?.close()
    }
  }, [gameId])

  return state
}
