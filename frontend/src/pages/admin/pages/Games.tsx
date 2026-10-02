import React from 'react'
import { GameTable } from '../components/GameTable'
import { useGameStore } from '../../../store/game.store'

export const Games: React.FC = () => {
  const { gamesList } = useGameStore()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Game Catalog Management</h1>
        <p className="text-xs text-slate-400">
          Monitor house edges, active betting thresholds, and maintenance toggles
        </p>
      </div>

      <GameTable games={gamesList} />
    </div>
  )
}

