import React from 'react'
import { formatMultiplier } from '../../../utils/formatters'

export interface AviatorHistoryProps {
  history: number[]
}

export const AviatorHistory: React.FC<AviatorHistoryProps> = ({ history }) => {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto py-1 scrollbar-thin">
      {history.map((mult, idx) => {
        const isSuper = mult >= 10.0
        const isHigh = mult >= 2.0
        return (
          <span
            key={idx}
            className={`px-2.5 py-1 rounded-lg text-xs font-mono font-black shrink-0 border transition-all ${
              isSuper
                ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                : isHigh
                ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
            }`}
          >
            {formatMultiplier(mult)}
          </span>
        )
      })}
    </div>
  )
}

