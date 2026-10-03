import React from 'react'
import { Gamepad2 } from 'lucide-react'
import { LobbyHome } from '../../components/games/LobbyHome'

export const Games: React.FC = () => (
  <div className="space-y-5">
    <div className="flex items-center gap-3">
      <Gamepad2 className="w-6 h-6 text-brand-blue" />
      <div>
        <h2 className="text-2xl font-black text-white">Casino</h2>
        <p className="text-xs text-slate-400">4 live games • more coming soon</p>
      </div>
    </div>
    <LobbyHome showHero={false} />
  </div>
)
