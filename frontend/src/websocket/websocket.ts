import { WS_BASE_URL } from '../utils/constants'
import { WS_EVENTS_V1, type WsMessage } from './events'
import { setServerTime } from '../utils/serverTime'
import { useGameStore } from '../store/game.store'
import { useAuthStore } from '../store/auth.store'

type EventHandler = (payload: any) => void

class WebSocketManager {
  private socket: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectDelay = 30000
  private baseReconnectDelay = 1000
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private eventHandlers: Map<string, Set<EventHandler>> = new Map()
  private isExplicitlyClosed = false

  public connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return
    }

    this.isExplicitlyClosed = false
    useGameStore.getState().setIsReconnecting(this.reconnectAttempts > 0)

    try {
      this.socket = new WebSocket(WS_BASE_URL)
    } catch (e) {
      console.error('[WS] Connection initialization error:', e)
      this.scheduleReconnect()
      return
    }

    this.socket.onopen = () => {
      console.log('[WS] Connected to gaming gateway')
      this.reconnectAttempts = 0
      useGameStore.getState().setWsConnected(true)
      useGameStore.getState().setIsReconnecting(false)
      this.startHeartbeat()

      // Authenticate socket if accessToken is available
      const token = useAuthStore.getState().accessToken
      if (token) {
        this.send(WS_EVENTS_V1.AUTH_TICKET, { token })
      }
    }

    this.socket.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data)

        // Sync server time if attached
        if (msg.serverTime) {
          setServerTime(msg.serverTime)
        }

        // Handle system level events
        if (msg.event === WS_EVENTS_V1.MAINTENANCE) {
          useGameStore.getState().setMaintenance(true)
        }

        // Dispatch to registered event listeners
        const handlers = this.eventHandlers.get(msg.event)
        if (handlers) {
          handlers.forEach((fn) => fn(msg.payload))
        }
      } catch (err) {
        console.warn('[WS] Failed to parse message:', err)
      }
    }

    this.socket.onclose = () => {
      useGameStore.getState().setWsConnected(false)
      this.stopHeartbeat()
      if (!this.isExplicitlyClosed) {
        this.scheduleReconnect()
      }
    }

    this.socket.onerror = (err) => {
      console.error('[WS] Error:', err)
    }
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true
    this.stopHeartbeat()
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
    useGameStore.getState().setWsConnected(false)
    useGameStore.getState().setIsReconnecting(false)
  }

  public send(event: string, payload: unknown): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const msg: WsMessage = {
        event,
        payload,
        timestamp: Date.now(),
      }
      this.socket.send(JSON.stringify(msg))
    }
  }

  public on(event: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set())
    }
    this.eventHandlers.get(event)!.add(handler)

    // Return unbind function
    return () => {
      this.eventHandlers.get(event)?.delete(handler)
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatInterval = setInterval(() => {
      this.send(WS_EVENTS_V1.PING, { clientTime: Date.now() })
    }, 15000)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts++
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(1.5, this.reconnectAttempts),
      this.maxReconnectDelay
    )
    console.log(`[WS] Reconnecting in ${Math.round(delay / 1000)}s...`)
    useGameStore.getState().setIsReconnecting(true)
    setTimeout(() => {
      if (!this.isExplicitlyClosed) {
        this.connect()
      }
    }, delay)
  }
}

export const wsClient = new WebSocketManager()
