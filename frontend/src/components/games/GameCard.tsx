import React from 'react'
import { Link } from 'react-router-dom'
import { Play, ShieldCheck, Users } from 'lucide-react'
import type { GameMetadata } from '../../types/game.types'
import { LiveBadge } from './LiveBadge'
import { t as tr } from '../../i18n'

export interface GameCardProps {
  game: GameMetadata
}

export const GameCard: React.FC<GameCardProps> = ({ game }) => {
  const isAvailable = game.isActive && !game.comingSoon

  const routeMap: Record<string, string> = {
    aviator: '/games/aviator',
    color: '/games/color',
    mines: '/games/mines',
    cricket: '/games/cricket',
  }

  const coverMap: Record<string, string> = {
    aviator: '/games/aviator/cover.jpg',
    color: '/games/color/cover.svg',
    mines: '/games/mines/cover.svg',
  }
  const cover = coverMap[game.id]

  const gradientMap: Record<string, string> = {
    aviator: 'from-rose-500/20 via-orange-500/10 to-dark-card border-rose-500/30',
    color: 'from-emerald-500/20 via-teal-500/10 to-dark-card border-emerald-500/30',
    mines: 'from-amber-500/20 via-yellow-500/10 to-dark-card border-amber-500/30',
    cricket: 'from-blue-500/20 via-indigo-500/10 to-dark-card border-blue-500/30',
  }

  return (
    <div
      className={`group relative rounded-2xl border p-5 transition-all duration-300 bg-gradient-to-b ${
        gradientMap[game.id] || 'bg-dark-card border-dark-border'
      } hover:translate-y-[-2px] hover:shadow-2xl flex flex-col justify-between`}
    >
      <div>
        {cover && (
          <Link to={routeMap[game.id] || '/games'} className="block -mx-5 -mt-5 mb-4 overflow-hidden rounded-t-2xl">
            <img src={cover} alt={`${game.name} cover`} className="w-full h-36 object-cover transition-transform duration-300 group-hover:scale-105" />
          </Link>
        )}
        <div className="flex items-center justify-between gap-2 mb-3">
          {isAvailable ? (
            <LiveBadge label={tr('AVAILABLE')} />
          ) : game.comingSoon ? (
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
              {tr('Coming Soon')}
            </span>
          ) : (
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
              {tr('Maintenance')}
            </span>
          )}
          <div className="flex items-center gap-1 text-[11px] font-bold text-slate-400">
            <Users className="w-3.5 h-3.5" />
            {game.currentPlayersCount > 0 && <span>{game.currentPlayersCount} online</span>}
          </div>
        </div>

        <h3 className="text-xl font-black text-white group-hover:text-emerald-400 transition-colors">
          {game.name}
        </h3>
        <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
          {game.description}
        </p>

        <div className="flex items-center gap-3 mt-4 text-[11px] font-semibold text-slate-400">
          <span>RTP: {game.rtpPercent}%</span>
          <span>•</span>
          <span className="flex items-center gap-1 text-cyan-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>{tr('Fair RNG')}</span>
          </span>
        </div>
      </div>

      <div className="mt-6 pt-4 border-t border-dark-border/50">
        {isAvailable ? (
          <Link
            to={routeMap[game.id] || '/games'}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-bg font-extrabold text-xs transition-all shadow-md shadow-emerald-500/20"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{tr('PLAY NOW')}</span>
          </Link>
        ) : (
          <button
            disabled
            className="w-full py-2.5 rounded-xl bg-dark-elevated text-slate-500 text-xs font-bold cursor-not-allowed"
          >
            Coming Soon
          </button>
        )}
      </div>
    </div>
  )
}
