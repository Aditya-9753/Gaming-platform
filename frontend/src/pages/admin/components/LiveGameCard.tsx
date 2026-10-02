import React from 'react'
import type { GameMetadata } from '../../../types/game.types'

export interface LiveGameCardProps {
  game: GameMetadata
  currentRoundNumber?: number
}

export const LiveGameCard: React.FC<LiveGameCardProps> = ({ game, currentRoundNumber = 8492 }) => {
  return (
    <div className="p-5 rounded-2xl bg-dark-card border border-dark-border space-y-4 shadow-xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
          <h4 className="text-base font-black text-white">{game.name}</h4>
        </div>
        <span className="text-[10px] font-mono text-slate-400">Round #{currentRoundNumber}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="p-3 rounded-xl bg-dark-elevated border border-dark-border">
          <span className="text-slate-400 block mb-0.5">Online Players</span>
          <span className="text-base font-black text-white">{game.currentPlayersCount}</span>
        </div>
        <div className="p-3 rounded-xl bg-dark-elevated border border-dark-border">
          <span className="text-slate-400 block mb-0.5">RTP Setting</span>
          <span className="text-base font-black text-emerald-400">{game.rtpPercent}%</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-dark-border">
        <span>Node: cluster-ap-south-1</span>
        <span className="text-emerald-400 font-semibold">100% Health</span>
      </div>
    </div>
  )
}
