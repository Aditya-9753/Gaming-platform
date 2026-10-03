import React from 'react'
import { Link } from 'react-router-dom'
import type { LobbyGame } from '../../utils/lobbyGames'
import { GameArt, hasGameArt } from './GameArt'

/** Portrait lobby tile (tag on top, big title, illustration). */
export const GameTile: React.FC<{ game: LobbyGame; disabled?: boolean }> = ({ game, disabled = false }) => {
  const playable = Boolean(game.live && game.to && !disabled)
  const art = hasGameArt(game.id)
  const body = (
    <div className="space-y-1.5">
      <div className={`relative aspect-[3/4] overflow-hidden rounded-2xl bg-gradient-to-b ${game.gradient} shadow-lg transition-transform duration-200 ${playable ? 'group-hover:-translate-y-1 group-active:scale-[0.98]' : ''}`}>
        {art && (
          <>
            <GameArt id={game.id} className={`absolute inset-0 h-full w-full transition-transform duration-300 ${playable ? 'group-hover:scale-105' : ''}`} />
            {/* keeps the title readable over the scene */}
            <div className="absolute inset-x-0 top-0 h-[42%] bg-gradient-to-b from-black/75 via-black/35 to-transparent" />
          </>
        )}
        <span className="absolute left-1/2 top-0 z-10 -translate-x-1/2 rounded-b-md bg-black/55 px-2 py-0.5 text-[9px] font-black tracking-wider text-white/90">{game.tag}</span>
        <h3 className="absolute inset-x-2 top-6 z-10 text-center text-[clamp(14px,4.2vw,22px)] font-black uppercase leading-[1.05] text-white drop-shadow-[0_2px_0_rgba(0,0,0,0.35)]">
          {game.title}
        </h3>
        {!art && <span aria-hidden className="absolute inset-x-0 bottom-3 text-center text-[clamp(36px,12vw,64px)] leading-none drop-shadow-[0_6px_10px_rgba(0,0,0,0.35)]">{game.art}</span>}
        {!playable && (
          <div className="absolute inset-0 z-10 flex items-end justify-center bg-black/45 pb-2">
            <span className="rounded-full bg-black/70 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-amber-300">
              {disabled ? 'Maintenance' : 'Coming soon'}
            </span>
          </div>
        )}
      </div>
      <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400">
        {playable
          ? <><span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />Live now</>
          : <><span className="h-1.5 w-1.5 rounded-full bg-slate-600" />{game.title}</>}
      </p>
    </div>
  )
  return playable
    ? <Link to={game.to!} className="group block" aria-label={`Play ${game.title}`}>{body}</Link>
    : <div className="group block cursor-default select-none" aria-label={`${game.title} — coming soon`}>{body}</div>
}

/** Section heading + 3-per-row on phones, more on larger screens. */
export const GameTileSection: React.FC<{ title: string; icon?: React.ReactNode; games: LobbyGame[]; disabledIds?: Set<string>; action?: React.ReactNode }> = ({ title, icon, games, disabledIds, action }) => (
  <section className="space-y-3">
    <div className="flex items-center justify-between">
      <h2 className="flex items-center gap-2 text-lg font-black text-white">{icon}{title}</h2>
      {action}
    </div>
    <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-6">
      {games.map((g) => <GameTile key={g.id} game={g} disabled={disabledIds?.has(g.id)} />)}
    </div>
  </section>
)
