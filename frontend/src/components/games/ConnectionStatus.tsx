import React from 'react'
import { Wifi, WifiOff, Loader2 } from 'lucide-react'
import { useGameStore } from '../../store/game.store'

export interface ConnectionStatusProps {
  /** Status of the page's own game socket; falls back to the global client. */
  connected?: boolean
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({ connected }) => {
  const store = useGameStore()
  const wsConnected = connected ?? store.wsConnected
  const isReconnecting = connected === undefined && store.isReconnecting

  if (isReconnecting) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-amber-400">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span>Reconnecting...</span>
      </div>
    )
  }

  if (wsConnected) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-emerald-400">
        <Wifi className="w-3.5 h-3.5" />
        <span>Live Sync</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-400">
      <WifiOff className="w-3.5 h-3.5" />
      <span>Connecting…</span>
    </div>
  )
}

