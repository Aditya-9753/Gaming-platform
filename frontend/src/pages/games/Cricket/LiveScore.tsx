import React from 'react'
import { Activity } from 'lucide-react'

export interface LiveScoreProps {
  teamA: string
  teamB: string
  scoreA: string
  scoreB: string
  overs: string
  currentOverBalls: string[]
}

export const LiveScore: React.FC<LiveScoreProps> = ({
  teamA,
  teamB,
  scoreA,
  scoreB,
  overs,
  currentOverBalls,
}) => {
  return (
    <div className="p-5 rounded-2xl bg-dark-card border border-dark-border space-y-4">
      <div className="flex items-center justify-between text-xs text-slate-400 font-bold">
        <span className="flex items-center gap-1.5 text-rose-400">
          <Activity className="w-4 h-4 animate-pulse" />
          <span>LIVE T20 MATCH</span>
        </span>
        <span>Overs: {overs}</span>
      </div>

      <div className="flex items-center justify-between text-base sm:text-lg font-black text-white">
        <div>
          <span>{teamA}</span>
          <span className="ml-2 font-mono text-emerald-400">{scoreA}</span>
        </div>
        <span className="text-xs text-slate-500 font-normal">vs</span>
        <div>
          <span>{teamB}</span>
          <span className="ml-2 font-mono text-slate-300">{scoreB}</span>
        </div>
      </div>

      <div className="pt-2 border-t border-dark-border flex items-center gap-2">
        <span className="text-xs text-slate-400 font-semibold">This Over:</span>
        <div className="flex items-center gap-1.5">
          {currentOverBalls.map((b, i) => (
            <span
              key={i}
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-black font-mono ${
                b === 'W'
                  ? 'bg-rose-500 text-white'
                  : b === '4' || b === '6'
                  ? 'bg-emerald-500 text-dark-bg'
                  : 'bg-dark-elevated text-slate-300 border border-dark-border'
              }`}
            >
              {b}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

