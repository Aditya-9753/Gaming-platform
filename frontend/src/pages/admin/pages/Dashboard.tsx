import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, Bot, Gamepad2, IndianRupee, Landmark, RefreshCw, Ticket, TrendingUp, UserPlus, Users } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { HourlyFlowChart, type HourPoint } from '../components/HourlyFlowChart'

interface Kpis {
  players_total: number; signups_today: number; suspended: number; active_15m: number; active_24h: number
  players_today: number; bets_today: number; wagered_today: number; paid_today: number; house_today: number
  hold_pct_today: number; player_balances: number; in_open_bets: number; open_tickets: number
}
interface GameRow { game_id: string; name: string; is_active: boolean; round_no: number | null; round_status: string | null; bets: number; players: number; wagered: number; paid: number; house_net: number; last_bet_at: string | null }
interface RecentBet { username: string; game_id: string; amount: number; pick: string; status: string; payout: number; multiplier: number | null; at: string }
interface Signup { username: string; joined_at: string | null; last_login_at: string | null; balance: number }
interface TopPlayer { username: string; bets: number; wagered: number; won: number; net: number }
interface Live { generated_at: string; include_bots: boolean; kpis: Kpis; games: GameRow[]; hourly: HourPoint[]; recent_bets: RecentBet[]; signups: Signup[]; top_players: TopPlayer[] }

const REFRESH_MS = 5000
const GAME_LABEL: Record<string, string> = { aviator: 'Aviator', mines: 'Mines', cricket: 'Cricket', color: 'Color (old)', wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m' }

const ago = (iso: string | null, now: number) => {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

const Kpi: React.FC<{ label: string; value: string; sub?: string; icon: React.ReactNode; tone?: string }> = ({ label, value, sub, icon, tone = 'text-white' }) => (
  <div className="rounded-2xl border border-dark-border bg-dark-card p-4">
    <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">{icon}{label}</p>
    <p className={`mt-2 font-mono text-xl font-black ${tone}`}>{value}</p>
    {sub && <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p>}
  </div>
)

const statusTone: Record<string, string> = { WON: 'text-emerald-400', LOST: 'text-rose-400', PLACED: 'text-amber-300', REFUNDED: 'text-slate-300' }

export const Dashboard: React.FC = () => {
  const [data, setData] = useState<Live | null>(null)
  const [includeBots, setIncludeBots] = useState(false)
  const [error, setError] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [loading, setLoading] = useState(false)
  const inflight = useRef(false)

  const load = useCallback(async () => {
    if (inflight.current) return
    inflight.current = true
    setLoading(true)
    try {
      const { data: body } = await apiClient.get<Live>('/admin/dashboard/live', { params: { include_bots: includeBots } })
      setData(body)
      setError(false)
    } catch {
      setError(true)
    } finally {
      inflight.current = false
      setLoading(false)
    }
  }, [includeBots])

  useEffect(() => {
    void load()
    const poll = setInterval(() => { if (document.visibilityState === 'visible') void load() }, REFRESH_MS)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    const onVisible = () => { if (document.visibilityState === 'visible') void load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(poll); clearInterval(tick); document.removeEventListener('visibilitychange', onVisible) }
  }, [load])

  const k = data?.kpis

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Live Operations</h1>
          <p className="flex items-center gap-2 text-xs text-slate-400">
            <span className={`h-2 w-2 rounded-full ${error ? 'bg-rose-500' : 'animate-pulse bg-emerald-500'}`} />
            {error ? 'Connection problem — retrying' : data ? `Real data · updated ${ago(data.generated_at, now)} · refreshes every 5s` : 'Loading…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dark-border bg-dark-card px-3 py-2 text-xs text-slate-300">
            <input type="checkbox" checked={includeBots} onChange={(e) => setIncludeBots(e.target.checked)} className="rounded" />
            <Bot className="h-4 w-4 text-slate-400" />Include simulated players
          </label>
          <button type="button" aria-label="Refresh now" onClick={() => void load()} className="rounded-xl border border-dark-border bg-dark-card p-2 text-slate-300 hover:text-white"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /></button>
        </div>
      </div>

      {!data || !k ? <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">{error ? 'Metrics could not be loaded.' : 'Loading live metrics…'}</p> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Players" value={k.players_total.toLocaleString()} sub={`+${k.signups_today} today · ${k.suspended} suspended`} icon={<Users className="h-4 w-4 text-emerald-400" />} />
            <Kpi label="Active now" value={k.active_15m.toLocaleString()} sub={`last 15 min · ${k.active_24h} played in 24h`} icon={<Activity className="h-4 w-4 text-cyan-400" />} />
            <Kpi label="Bets today" value={k.bets_today.toLocaleString()} sub={`${k.players_today} players`} icon={<Gamepad2 className="h-4 w-4 text-purple-400" />} />
            <Kpi label="Wagered today" value={formatPaiseToRupee(k.wagered_today)} sub={`paid ${formatPaiseToRupee(k.paid_today)}`} icon={<IndianRupee className="h-4 w-4 text-sky-400" />} />
            <Kpi label="House today" value={`${k.house_today >= 0 ? '+' : '−'}${formatPaiseToRupee(Math.abs(k.house_today))}`} sub={`hold ${k.hold_pct_today}% of settled bets`} tone={k.house_today >= 0 ? 'text-emerald-400' : 'text-rose-400'} icon={<Landmark className="h-4 w-4 text-emerald-400" />} />
            <Kpi label="Player balances" value={formatPaiseToRupee(k.player_balances)} sub={`${formatPaiseToRupee(k.in_open_bets)} in open bets`} icon={<TrendingUp className="h-4 w-4 text-amber-400" />} />
            <Kpi label="New sign-ups" value={k.signups_today.toLocaleString()} sub="since midnight IST" icon={<UserPlus className="h-4 w-4 text-pink-400" />} />
            <Kpi label="Open tickets" value={k.open_tickets.toLocaleString()} sub="support queue" icon={<Ticket className="h-4 w-4 text-orange-400" />} />
          </div>

          <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
            <h2 className="mb-1 text-sm font-black text-white">Last 24 hours — wagered vs paid</h2>
            <p className="mb-3 text-[11px] text-slate-500">Hourly totals from real bets{data.include_bots ? ' (simulated players included)' : ''}</p>
            <HourlyFlowChart data={data.hourly} />
          </section>

          <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
            <h2 className="mb-3 text-sm font-black text-white">Games today</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-2">Game</th><th className="py-2">Status</th><th className="py-2">Current round</th><th className="py-2 text-right">Bets</th><th className="py-2 text-right">Players</th><th className="py-2 text-right">Wagered</th><th className="py-2 text-right">Paid</th><th className="py-2 text-right">House</th><th className="py-2 text-right">Last bet</th></tr></thead>
                <tbody>
                  {data.games.filter((g) => g.game_id !== 'color').map((g) => (
                    <tr key={g.game_id} className="border-t border-dark-border/50">
                      <td className="py-2 font-bold text-white">{GAME_LABEL[g.game_id] ?? g.name}</td>
                      <td className="py-2">{g.is_active ? <span className="text-emerald-400">● Live</span> : <span className="text-amber-300">❚❚ Paused</span>}</td>
                      <td className="py-2 font-mono text-slate-300">{g.round_no ? `#${g.round_no}` : '—'} <span className="text-slate-500">{g.round_status?.toLowerCase() ?? ''}</span></td>
                      <td className="py-2 text-right">{g.bets.toLocaleString()}</td>
                      <td className="py-2 text-right">{g.players.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.wagered)}</td>
                      <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.paid)}</td>
                      <td className={`py-2 text-right font-mono font-bold ${g.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{g.house_net >= 0 ? '+' : '−'}{formatPaiseToRupee(Math.abs(g.house_net))}</td>
                      <td className="py-2 text-right text-slate-400">{ago(g.last_bet_at, now)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
              <h2 className="mb-3 text-sm font-black text-white">Latest bets</h2>
              {data.recent_bets.length === 0 ? <p className="text-xs text-slate-400">No bets from real players yet.</p> : (
                <div className="max-h-[420px] overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-dark-card"><tr className="text-left text-slate-400"><th className="py-1.5">Player</th><th className="py-1.5">Game</th><th className="py-1.5">Pick</th><th className="py-1.5 text-right">Bet</th><th className="py-1.5 text-right">Result</th><th className="py-1.5 text-right">When</th></tr></thead>
                    <tbody>
                      {data.recent_bets.map((b, i) => (
                        <tr key={i} className="border-t border-dark-border/50">
                          <td className="py-1.5 font-bold text-white">{b.username}</td>
                          <td className="py-1.5 text-slate-300">{GAME_LABEL[b.game_id] ?? b.game_id}</td>
                          <td className="py-1.5 text-slate-400">{b.pick}</td>
                          <td className="py-1.5 text-right font-mono">{formatPaiseToRupee(b.amount)}</td>
                          <td className={`py-1.5 text-right font-bold ${statusTone[b.status] ?? 'text-slate-300'}`}>{b.status === 'WON' ? `+${formatPaiseToRupee(b.payout)}${b.multiplier ? ` (${b.multiplier.toFixed(2)}x)` : ''}` : b.status === 'PLACED' ? 'Pending' : b.status}</td>
                          <td className="py-1.5 text-right text-slate-500">{ago(b.at, now)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <div className="space-y-6">
              <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
                <h2 className="mb-3 text-sm font-black text-white">Top players today</h2>
                {data.top_players.length === 0 ? <p className="text-xs text-slate-400">No settled bets today.</p> : data.top_players.map((p, i) => (
                  <div key={p.username} className="flex items-center justify-between border-t border-dark-border/50 py-1.5 text-xs first:border-0">
                    <span className="text-slate-300"><span className="mr-2 text-slate-500">#{i + 1}</span><b className="text-white">{p.username}</b> · {p.bets} bets</span>
                    <span className={`font-mono font-bold ${p.net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{p.net >= 0 ? '+' : '−'}{formatPaiseToRupee(Math.abs(p.net))}</span>
                  </div>
                ))}
              </section>
              <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
                <h2 className="mb-3 text-sm font-black text-white">Newest players</h2>
                {data.signups.length === 0 ? <p className="text-xs text-slate-400">No players yet.</p> : data.signups.map((s) => (
                  <div key={s.username} className="flex items-center justify-between border-t border-dark-border/50 py-1.5 text-xs first:border-0">
                    <span><b className="text-white">{s.username}</b> <span className="text-slate-500">joined {ago(s.joined_at, now)}</span></span>
                    <span className="font-mono text-slate-300">{formatPaiseToRupee(s.balance)}</span>
                  </div>
                ))}
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
