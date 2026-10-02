import React from 'react'
import type { GameRound } from '../../types/game.types'
import { formatMultiplier } from '../../utils/formatters'

export interface GameHistoryProps {
  rounds: GameRound[]
  gameType?: 'aviator' | 'color'
}

export const GameHistory: React.FC<GameHistoryProps> = ({ rounds, gameType = 'aviator' }) => {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto py-2 scrollbar-thin">
      {rounds.map((round) => {
        if (gameType === 'aviator') {
          const mult = round.crashMultiplier || 1.0
          const isHigh = mult >= 2.0
          return (
            <span
              key={round.id}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold shrink-0 border ${
                isHigh
                  ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                  : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
              }`}
            >
              {formatMultiplier(mult)}
            </span>
          )
        }

        // Color prediction circle
        const color = round.winningColor || 'green'
        const colorMap = {
          green: 'bg-emerald-500 text-dark-bg',
          red: 'bg-rose-500 text-white',
          violet: 'bg-purple-500 text-white',
        }

        return (
          <span
            key={round.id}
            className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${colorMap[color]}`}
          >
            {round.winningNumber ?? '?'}
          </span>
        )
      })}
    </div>
  )
}

