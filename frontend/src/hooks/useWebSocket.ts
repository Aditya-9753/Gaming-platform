import { useEffect } from 'react'
import { wsClient } from '../websocket/websocket'

export function useWebSocket(
  event: string,
  handler: (data: unknown) => void,
  deps: unknown[] = []
): void {
  useEffect(() => {
    const off = wsClient.on(event, handler)
    return off
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event, ...deps])
}

