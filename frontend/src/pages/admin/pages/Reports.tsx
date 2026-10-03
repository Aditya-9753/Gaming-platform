import React, { useCallback, useEffect, useState } from 'react'
import { ArrowDownLeft, IndianRupee, Percent, RefreshCw, TrendingUp, UserPlus, Users } from 'lucide-react'
import { StatCard } from '../components/StatCard'
import { HourlyFlowChart } from '../components/HourlyFlowChart'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { showToast } from '../../../components/common/Toast'

interface Totals { wagered: number; paid: number; house_net: number; bets: number; players: number; hold_pct: number; signups?: number }
interface DayPoint extends Totals { date: string; label: string; signups: number }
interface MinutePoint extends Totals { label: string }
interface GameTotals extends Totals { game_id: string }

interface LiveReport {
  generated_at: string
  today: Totals
  window: Totals
  daily: DayPoint[]
  last_hour: MinutePoint[]
  games: GameTotals[]
}

const REFRESH_MS = 5000
const RANGES = [7, 14, 30]
const GAME_LABEL: Record<string, string> = {
  aviator: 'Aviator', mines: 'Mines', cricket: 'Cricket', color: 'Color (old)',
  wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m',
}

export const Reports: React.FC = () => {
  const [report, setReport] = useState<LiveReport | null>(null)
  const [failed, setFailed] = useState(false)
  const [days, setDays] = useState(7)
  const [includeBots, setIncludeBots] = useState(false)
  const [live, setLive] = useState(true)

  const load = useCallback(async (quiet = false) => {
    try {
      const { data } = await apiClient.get<LiveReport>('/admin/reports/live', { params: { days, include_bots: includeBots } })
      setReport(data)
      setFailed(false)
    } catch {
      setFailed(true)
      if (!quiet) showToast({ title: 'Reports unavailable', message: 'Report metrics could not be loaded.', type: 'error' })
    }
  }, [days, includeBots])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!live) return
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load(true) }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [live, load])

  const toPoints = (rows: Array<Totals & { label: string }>) => rows.map((r) => ({ hour: r.label, wagered: r.wagered, paid: r.paid, bets: r.bets }))
  const maxGame = Math.max(1, ...(report?.games ?? []).map((g) => g.wagered))
  const t = report?.today
  const w = report?.window

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Reports & Analytics</h1>
          <p className="text-xs text-slate-400">
            Live figures, refreshed every {REFRESH_MS / 1000}s • India time • {includeBots ? 'including' : 'excluding'} lobby bots
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
          <div className="inline-flex rounded-xl border border-dark-border bg-dark-elevated p-0.5">
            {RANGES.map((d) => (
              <button key={d} type="button" onClick={() => setDays(d)} className={`rounded-lg px-3 py-1.5 ${days === d ? 'bg-purple-500 text-white' : 'text-slate-400 hover:text-white'}`}>{d}d</button>
            ))}
          </div>
          <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-slate-300">
            <input type="checkbox" checked={includeBots} onChange={(e) => setIncludeBots(e.target.checked)} /> Bots
          </label>
          <button type="button" onClick={() => setLive((v) => !v)} className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 ${live ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-dark-border bg-dark-elevated text-slate-400'}`}>
            <RefreshCw className={`h-3.5 w-3.5 ${live ? 'animate-spin [animation-duration:3s]' : ''}`} />
            {live ? 'Live' : 'Paused'}
          </button>
        </div>
      </div>

      {!report || !t || !w ? (
        <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">{failed ? 'Report metrics could not be loaded.' : 'Loading report metrics…'}</p>
      ) : <>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Wagered today" value={formatPaiseToRupee(t.wagered)} change={`${days}d: ${formatPaiseToRupee(w.wagered)}`} icon={<IndianRupee className="h-5 w-5 text-emerald-400" />} />
          <StatCard label="Paid today" value={formatPaiseToRupee(t.paid)} change={`${days}d: ${formatPaiseToRupee(w.paid)}`} icon={<ArrowDownLeft className="h-5 w-5 text-purple-400" />} />
          <StatCard label="House net today" value={formatPaiseToRupee(t.house_net)} change={`${days}d: ${formatPaiseToRupee(w.house_net)}`} isPositive={t.house_net >= 0} icon={<TrendingUp className="h-5 w-5 text-amber-400" />} />
          <StatCard label="Hold % today" value={`${t.hold_pct.toFixed(2)}%`} change={`${days}d: ${w.hold_pct.toFixed(2)}%`} icon={<Percent className="h-5 w-5 text-cyan-400" />} />
          <StatCard label="Bets today" value={t.bets.toLocaleString('en-IN')} change={`${days}d: ${w.bets.toLocaleString('en-IN')}`} icon={<IndianRupee className="h-5 w-5 text-slate-300" />} />
          <StatCard label="Players today" value={t.players} change={`${days}d: ${w.players}`} icon={<Users className="h-5 w-5 text-slate-300" />} />
          <StatCard label="Sign-ups today" value={t.signups ?? 0} change={`${days}d: ${w.signups ?? 0}`} icon={<UserPlus className="h-5 w-5 text-slate-300" />} />
          <StatCard label="Last 60 min" value={formatPaiseToRupee(report.last_hour.reduce((s, m) => s + m.wagered, 0))} change={`${report.last_hour.reduce((s, m) => s + m.bets, 0)} bets`} icon={<RefreshCw className="h-5 w-5 text-slate-300" />} />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5 shadow-xl">
            <h3 className="text-base font-bold text-white">Last 60 minutes <span className="text-xs font-normal text-slate-500">• per minute</span></h3>
            <HourlyFlowChart data={toPoints(report.last_hour)} labelEvery={10} timeLabel="Minute (IST)" ariaLabel="Wagered and paid per minute, last 60 minutes" />
          </section>
          <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5 shadow-xl">
            <h3 className="text-base font-bold text-white">Daily trend <span className="text-xs font-normal text-slate-500">• last {days} days</span></h3>
            <HourlyFlowChart data={toPoints(report.daily)} labelEvery={days > 14 ? 5 : days > 7 ? 2 : 1} timeLabel="Day" ariaLabel={`Wagered and paid per day, last ${days} days`} />
          </section>
        </div>

        <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5 shadow-xl">
          <h3 className="text-base font-bold text-white">By game <span className="text-xs font-normal text-slate-500">• last {days} days</span></h3>
          {report.games.length === 0 ? <p className="text-sm text-slate-400">No bets in this period.</p> : (
            <div className="space-y-2.5">
              {report.games.map((g) => (
                <div key={g.game_id} className="grid grid-cols-[110px_1fr] items-center gap-3 text-xs sm:grid-cols-[130px_1fr_220px]">
                  <span className="font-bold text-white">{GAME_LABEL[g.game_id] ?? g.game_id}</span>
                  <div className="h-3 overflow-hidden rounded-full bg-dark-elevated">
                    <div className="h-full rounded-full bg-[#3987e5] transition-all duration-500" style={{ width: `${(g.wagered / maxGame) * 100}%` }} />
                  </div>
                  <span className="col-span-2 font-mono text-slate-400 sm:col-span-1 sm:text-right">
                    {formatPaiseToRupee(g.wagered)} • {g.bets} bets • <span className={g.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{formatPaiseToRupee(g.house_net)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <p className="text-[11px] text-slate-500">Updated {new Date(report.generated_at).toLocaleTimeString()}</p>
      </>}
    </div>
  )
}
