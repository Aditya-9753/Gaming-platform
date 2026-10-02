import React from 'react'
import { Clock } from 'lucide-react'

export interface GameTimerProps {
  remainingSeconds: number
  totalSeconds?: number
  label?: string
}

export const GameTimer: React.FC<GameTimerProps> = ({
  remainingSeconds,
  label = 'Next Round',
}) => {
  const isUrgent = remainingSeconds <= 5

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-mono font-bold ${
        isUrgent
          ? 'bg-rose-500/10 border-rose-500/30 text-rose-400 animate-pulse'
          : 'bg-dark-card border-dark-border text-slate-300'
      }`}
    >
      <Clock className="w-3.5 h-3.5 shrink-0" />
      <span>
        {label}: <span className="text-white">{Math.max(0, remainingSeconds)}s</span>
      </span>
    </div>
  )
}

