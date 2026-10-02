import React from 'react'
import type { GameMetadata } from '../../types/game.types'
import { GameCard } from './GameCard'

export interface GameGridProps {
  games: GameMetadata[]
}

export const GameGrid: React.FC<GameGridProps> = ({ games }) => {
  if (games.length === 0) {
    return <p className="rounded-2xl border border-dark-border bg-dark-card p-6 text-sm text-slate-400">No games are currently available. Check back later or contact support if the issue persists.</p>
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {games.map((game) => (
        <GameCard key={game.id} game={game} />
      ))}
    </div>
  )
}
