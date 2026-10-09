import React from 'react'
import { t as tr } from '../../../i18n'

export interface CricketBetRecord {
  id: string
  match: string
  team: string
  amountPaise: number
  status: 'won' | 'lost' | 'pending'
}

export interface CricketHistoryProps {
  bets: CricketBetRecord[]
}

export const CricketHistory: React.FC<CricketHistoryProps> = ({ bets }) => {
  if (bets.length === 0) {
    return <div className="text-center py-6 text-xs text-slate-500">{tr('No bets placed on cricket yet')}</div>
  }

  return (
    <div className="space-y-2">
      {bets.map((b) => (
        <div key={b.id} className="p-3 rounded-xl bg-dark-card border border-dark-border flex items-center justify-between text-xs">
          <div>
            <span className="font-bold text-white block">{b.team}</span>
            <span className="text-[10px] text-slate-400">{b.match}</span>
          </div>
          <span className="font-mono font-bold text-slate-300">₹{(b.amountPaise / 100).toFixed(0)}</span>
        </div>
      ))}
    </div>
  )
}

