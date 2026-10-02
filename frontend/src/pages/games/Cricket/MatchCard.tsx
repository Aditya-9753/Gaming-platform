import React from 'react'

export interface MatchCardProps {
  title: string
  team1: string
  team2: string
  odds1: number
  odds2: number
  onBet: (team: string, odds: number) => void
}

export const MatchCard: React.FC<MatchCardProps> = ({
  title,
  team1,
  team2,
  odds1,
  odds2,
  onBet,
}) => {
  return (
    <div className="p-4 rounded-2xl bg-dark-card border border-dark-border space-y-3">
      <span className="text-xs font-bold text-slate-400 block">{title}</span>
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => onBet(team1, odds1)}
          className="p-3 rounded-xl bg-dark-elevated hover:bg-slate-700 border border-dark-border text-left transition-all"
        >
          <span className="text-xs font-bold text-white block">{team1}</span>
          <span className="text-xs font-mono font-black text-emerald-400 mt-1 block">
            {odds1.toFixed(2)}× Odds
          </span>
        </button>

        <button
          onClick={() => onBet(team2, odds2)}
          className="p-3 rounded-xl bg-dark-elevated hover:bg-slate-700 border border-dark-border text-left transition-all"
        >
          <span className="text-xs font-bold text-white block">{team2}</span>
          <span className="text-xs font-mono font-black text-emerald-400 mt-1 block">
            {odds2.toFixed(2)}× Odds
          </span>
        </button>
      </div>
    </div>
  )
}

