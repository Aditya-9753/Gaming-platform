import React, { useCallback, useEffect, useState } from 'react'
import { Crown, Trophy, Sparkles } from 'lucide-react'
import { formatPaiseToRupee } from '../../utils/formatters'
import { apiClient } from '../../services/api'
import { useAuthStore } from '../../store/auth.store'

interface Entry {
  rank: number
  username: string
  total_wagered: number
  total_won: number
  net_profit: number
}

interface RecentWin {
  player: string
  game_id: string
  bet_amount: number
  payout_amount: number
  multiplier: number | null
  won_at: string | null
}

const GAME_LABEL: Record<string, string> = {
  teen_patti: 'Teen Patti',
  aviator: 'Aviator', mines: 'Mines', color: 'Color',
  wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m',
}
const PERIODS: Array<[string, string]> = [['DAILY', 'Today'], ['WEEKLY', 'This week'], ['ALL_TIME', 'All time']]
const podiumStyle = [
  'from-slate-300 to-slate-500 h-24',   // 2nd
  'from-amber-300 to-amber-600 h-32',   // 1st
  'from-orange-400 to-orange-700 h-20', // 3rd
]

export const Leaderboard: React.FC = () => {
  const { user } = useAuthStore()
  const [period, setPeriod] = useState('DAILY')
  const [entries, setEntries] = useState<Entry[]>([])
  const [wins, setWins] = useState<RecentWin[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [board, recent] = await Promise.all([
        apiClient.get<Entry[]>('/leaderboard', { params: { period, limit: 100 } }),
        apiClient.get<RecentWin[]>('/leaderboard/recent-wins', { params: { limit: 15 } }),
      ])
      setEntries(board.data)
      setWins(recent.data)
    } catch {
      /* keep last data */
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    setLoading(true)
    void load()
    const timer = setInterval(() => void load(), 30000)
    return () => clearInterval(timer)
  }, [load])

  const top3 = [entries[1], entries[0], entries[2]]
  const myRank = entries.find((e) => e.username === user?.username)

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Trophy className="h-7 w-7 text-amber-400" />
          <div>
            <h2 className="text-2xl font-black text-white">Leaderboard</h2>
            <p className="text-xs text-slate-400">Top winners by total winnings • updates every minute</p>
          </div>
        </div>
        <div className="inline-flex rounded-full border border-dark-border bg-dark-card p-0.5 text-xs font-bold">
          {PERIODS.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setPeriod(key)} className={`rounded-full px-4 py-1.5 ${period === key ? 'bg-amber-500 text-dark-bg' : 'text-slate-400'}`}>{label}</button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {entries.length >= 3 && (
            <div className="grid grid-cols-3 items-end gap-3 rounded-3xl bg-gradient-to-b from-amber-500/10 to-transparent p-4">
              {top3.map((entry, index) => entry && (
                <div key={entry.username} className="flex flex-col items-center gap-2 text-center">
                  {entry.rank === 1 && <Crown className="h-7 w-7 text-amber-400" />}
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-dark-elevated text-lg font-black text-white ring-2 ring-amber-400/60">{entry.username.charAt(0).toUpperCase()}</span>
                  <p className="max-w-full truncate text-xs font-bold text-white">{entry.username}</p>
                  <p className="font-mono text-xs font-bold text-emerald-400">{formatPaiseToRupee(entry.total_won)}</p>
                  <div className={`w-full rounded-t-xl bg-gradient-to-b ${podiumStyle[index]} flex items-start justify-center pt-2 text-2xl font-black text-white/90`}>{entry.rank}</div>
                </div>
              ))}
            </div>
          )}

          {myRank && (
            <p className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">You are ranked <b>#{myRank.rank}</b> with {formatPaiseToRupee(myRank.total_won)} won.</p>
          )}

          <div className="overflow-hidden rounded-2xl border border-dark-border bg-dark-card shadow-xl">
            <div className="grid grid-cols-[60px_1fr_1fr_1fr_1fr] bg-dark-elevated px-4 py-3 text-[11px] font-bold uppercase text-slate-500">
              <span>Rank</span><span>Player</span><span className="text-right">Wagered</span><span className="text-right">Won</span><span className="text-right">Net</span>
            </div>
            {loading ? <p className="p-5 text-sm text-slate-400">Loading rankings…</p> : entries.length === 0 ? <p className="p-5 text-sm text-slate-400">No rankings for this period yet — play a round to get on the board!</p> : entries.map((entry) => (
              <div key={`${entry.rank}-${entry.username}`} className={`grid grid-cols-[60px_1fr_1fr_1fr_1fr] items-center border-t border-dark-border/50 px-4 py-3 ${entry.username === user?.username ? 'bg-emerald-500/10' : ''}`}>
                <span className={`text-sm font-black ${entry.rank === 1 ? 'text-amber-400' : entry.rank === 2 ? 'text-slate-300' : entry.rank === 3 ? 'text-orange-400' : 'text-slate-500'}`}>#{entry.rank}</span>
                <span className="truncate text-xs font-bold text-white">{entry.username}</span>
                <span className="text-right font-mono text-xs text-slate-300">{formatPaiseToRupee(entry.total_wagered)}</span>
                <span className="text-right font-mono text-xs font-bold text-emerald-400">{formatPaiseToRupee(entry.total_won)}</span>
                <span className={`text-right font-mono text-xs ${entry.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{formatPaiseToRupee(entry.net_profit)}</span>
              </div>
            ))}
          </div>
        </div>

        <aside className="h-fit space-y-3 rounded-2xl border border-dark-border bg-dark-card p-4">
          <h3 className="flex items-center gap-2 text-sm font-black text-white"><Sparkles className="h-4 w-4 text-amber-400" />Winning information</h3>
          {wins.length === 0 ? <p className="text-xs text-slate-400">No wins yet.</p> : wins.map((win, index) => (
            <div key={index} className="flex items-center gap-3 rounded-xl bg-dark-elevated px-3 py-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/20 text-xs font-black text-amber-300">{win.player.charAt(0).toUpperCase()}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-bold text-white">{win.player}</p>
                <p className="text-[11px] text-slate-400">{GAME_LABEL[win.game_id] ?? win.game_id}{win.multiplier ? ` • ${win.multiplier.toFixed(2)}x` : ''}</p>
              </div>
              <span className="font-mono text-xs font-black text-emerald-400">{formatPaiseToRupee(win.payout_amount)}</span>
            </div>
          ))}
        </aside>
      </div>
      <p className="text-[11px] text-slate-500">Rankings are calculated from settled bets in virtual credits — not cash.</p>
    </div>
  )
}
