import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Flame, ShieldCheck, Zap, Users, ArrowRight } from 'lucide-react'
import { GameGrid } from '../../components/games/GameGrid'
import { DailyClaimCard } from '../../components/wallet/DailyClaimCard'
import { ProvablyFairBadge } from '../../components/games/ProvablyFairBadge'
import { useAuthStore } from '../../store/auth.store'
import { useGames } from '../../hooks/useGames'

export const Home: React.FC = () => {
  const { gamesList, fetchGames } = useGames()
  const { isAuthenticated } = useAuthStore()
  useEffect(() => { void fetchGames() }, [fetchGames])

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-emerald-950/60 via-dark-card to-dark-card border border-emerald-500/20 p-8 sm:p-12 shadow-2xl">
        <div className="max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-black uppercase tracking-wider">
            <Flame className="w-3.5 h-3.5 fill-current" />
            <span>Server-backed virtual-credit games</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-black text-white tracking-tight leading-tight">
            Play Fast. Win Fair. <br />
            <span className="bg-gradient-to-r from-emerald-400 to-teal-300 bg-clip-text text-transparent">
              Fair play. Live rounds.
            </span>
          </h1>

          <p className="text-sm sm:text-base text-slate-300 leading-relaxed max-w-xl">
            Play Aviator, Color Prediction, Mines, and Cricket with server-authoritative bets and provably fair results.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              to={isAuthenticated ? '/games/aviator' : '/register'}
              className="flex items-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 text-dark-bg font-black text-sm hover:from-emerald-400 hover:to-teal-400 transition-all shadow-lg shadow-emerald-500/25"
            >
              <span>{isAuthenticated ? 'PLAY AVIATOR' : 'CREATE PLAYER ACCOUNT'}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Floating perks */}
        <div className="mt-8 pt-8 border-t border-dark-border/60 grid grid-cols-2 sm:grid-cols-4 gap-4 text-left">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-black text-white block">Virtual Credits</span>
              <span className="text-[10px] text-slate-400 block">Server-backed wallet</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 shrink-0">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-black text-white block">HMAC-SHA256</span>
              <span className="text-[10px] text-slate-400 block">100% Provably Fair</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shrink-0">
              <Flame className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-black text-white block">Daily Credit Claim</span>
              <span className="text-[10px] text-slate-400 block">When eligible</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0">
              <Users className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-black text-white block">Live Players</span>
              <span className="text-[10px] text-slate-400 block">Multiplayer lobby</span>
            </div>
          </div>
        </div>
      </section>

      {/* Daily Bonus Claim Card */}
      {isAuthenticated && <DailyClaimCard />}

      {/* Games Catalog Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-black text-white">Live Game Lobby</h2>
            <p className="text-xs text-slate-400">
              Real-time multiplier & prediction rounds running 24/7
            </p>
          </div>
          <ProvablyFairBadge />
        </div>

        <GameGrid games={gamesList} />
      </section>
    </div>
  )
}
