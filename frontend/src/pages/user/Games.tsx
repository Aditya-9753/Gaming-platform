import React, { useEffect } from 'react'
import { GameGrid } from '../../components/games/GameGrid'
import { Gamepad2 } from 'lucide-react'
import { useGames } from '../../hooks/useGames'

export const Games: React.FC = () => {
  const { gamesList, fetchGames } = useGames()
  useEffect(() => { void fetchGames() }, [fetchGames])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Gamepad2 className="w-6 h-6 text-emerald-400" />
        <div>
          <h2 className="text-2xl font-black text-white">Game Lobby</h2>
          <p className="text-xs text-slate-400">
            All live games • Provably fair • Real-time multiplayer
          </p>
        </div>
      </div>

      <GameGrid games={gamesList} />
    </div>
  )
}
