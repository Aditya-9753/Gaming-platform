import React, { useState } from 'react'
import { History } from 'lucide-react'
import { MyBetsHistory } from '../../components/games/MyBetsHistory'

const FILTERS: Array<[string | undefined, string]> = [
  [undefined, 'All games'],
  ['aviator', 'Aviator'],
  ['wingo_30s', 'WinGo 30s'],
  ['wingo_1m', 'WinGo 1m'],
  ['wingo_3m', 'WinGo 3m'],
  ['wingo_5m', 'WinGo 5m'],
  ['mines', 'Mines'],
]

/** Every bet the player has made, across all games. */
export const BetHistory: React.FC = () => {
  const [gameId, setGameId] = useState<string | undefined>(undefined)
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex items-center gap-3">
        <History className="h-6 w-6 text-emerald-400" />
        <div>
          <h2 className="text-2xl font-black text-white">My Bets</h2>
          <p className="text-xs text-slate-400">Your complete game history. Cricket predictions are listed on the Cricket page.</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map(([id, label]) => (
          <button key={label} type="button" onClick={() => setGameId(id)} className={`rounded-full px-3 py-1.5 text-xs font-bold ${gameId === id ? 'bg-emerald-500 text-dark-bg' : 'border border-dark-border bg-dark-card text-slate-400 hover:text-white'}`}>{label}</button>
        ))}
      </div>
      <div className="rounded-2xl border border-dark-border bg-dark-card p-4">
        <MyBetsHistory gameId={gameId} pageSize={20} showGame />
      </div>
    </div>
  )
}
