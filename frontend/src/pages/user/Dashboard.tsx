import React from 'react'
import { Link } from 'react-router-dom'
import { Flame, Wallet, Trophy, Play, ArrowRight } from 'lucide-react'
import { BalanceCard } from '../../components/wallet/BalanceCard'
import { DailyClaimCard } from '../../components/wallet/DailyClaimCard'
import { useAuthStore } from '../../store/auth.store'
import { useWalletStore } from '../../store/wallet.store'
import { t as tr } from '../../i18n'

export const Dashboard: React.FC = () => {
  const { user } = useAuthStore()
  const { balance } = useWalletStore()

  return (
    <div className="space-y-6">
      {/* Welcome greeting */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white">
            Hello, {user?.username || tr('Player')} 👋
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            {tr('Welcome to your gaming dashboard. Live rounds are active.')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/wallet"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-dark-elevated text-xs font-bold text-slate-300 hover:text-white border border-dark-border"
          >
            <Wallet className="w-4 h-4 text-emerald-400" />
            <span>{tr('Manage Funds')}</span>
          </Link>
          <Link
            to="/leaderboard"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-dark-elevated text-xs font-bold text-slate-300 hover:text-white border border-dark-border"
          >
            <Trophy className="w-4 h-4 text-amber-400" />
            <span>{tr('Leaderboard')}</span>
          </Link>
        </div>
      </div>

      {/* Balance Card */}
      <BalanceCard balance={balance} />

      {/* Daily Claim Reward */}
      <DailyClaimCard />

      {/* Quick Launch Cards */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Flame className="w-4 h-4 text-orange-400 fill-current" />
            <span>{tr('Featured Games')}</span>
          </h3>
          <Link to="/games" className="text-xs text-emerald-400 hover:underline font-semibold flex items-center gap-1">
            <span>{tr('View All')}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Aviator featured banner */}
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-rose-950/60 via-dark-card to-dark-card border border-rose-500/30 p-6 flex flex-col justify-between shadow-xl">
            <div className="space-y-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-rose-500/20 text-rose-400 border border-rose-500/30 inline-block">
                {tr('CRASH MULTIPLIER')}
              </span>
              <h4 className="text-2xl font-black text-white">{tr('Aviator')}</h4>
              <p className="text-xs text-slate-300 leading-relaxed max-w-sm">
                {tr('Watch the curve climb up to 100x+. Cash out before the flight vanishes!')}
              </p>
            </div>
            <div className="pt-6">
              <Link
                to="/games/aviator"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-rose-500 hover:bg-rose-400 text-white font-black text-xs transition-all shadow-lg shadow-rose-500/25"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{tr('PLAY AVIATOR')}</span>
              </Link>
            </div>
          </div>

          {/* Color Prediction featured banner */}
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-950/60 via-dark-card to-dark-card border border-emerald-500/30 p-6 flex flex-col justify-between shadow-xl">
            <div className="space-y-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 inline-block">
                {tr('30-SEC CYCLES')}
              </span>
              <h4 className="text-2xl font-black text-white">{tr('Color Prediction')}</h4>
              <p className="text-xs text-slate-300 leading-relaxed max-w-sm">
                {tr('Pick Red, Green, or Violet. High RTP provably fair numbers drawn every 30s.')}
              </p>
            </div>
            <div className="pt-6">
              <Link
                to="/games/color"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-bg font-black text-xs transition-all shadow-lg shadow-emerald-500/25"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{tr('PLAY COLOR PREDICTION')}</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
