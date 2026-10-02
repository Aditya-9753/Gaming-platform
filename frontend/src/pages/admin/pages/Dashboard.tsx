import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, Bot, ChevronRight, Gamepad2, IndianRupee, Landmark, RefreshCw, Ticket, TrendingUp, UserPlus, Users } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { HourlyFlowChart, type HourPoint } from '../components/HourlyFlowChart'
import {
  BetsTable, GAME_LABEL, LiveDrawer, LiveStatus, PlayerLink, ago, money, signed,
  type BetRow, type PanelTarget,
} from '../components/LivePanels'

interface Kpis {
  players_total: number; signups_today: number; suspended: number; active_15m: number; active_24h: number
  players_today: number; bets_today: number; wagered_today: number; paid_today: number; house_today: number
  hold_pct_today: number; player_balances: number; in_open_bets: number; open_tickets: number
}
interface GameRow {
  game_id: string; name: string; is_active: boolean; round_no: number | null; round_status: string | null
  bets: number; players: number; wagered: number; paid: number; house_net: number; last_bet_at: string | null
  live?: React.ComponentProps<typeof LiveStatus>['live']
}
interface Signup { user_id: string; username: string; joined_at: string | null; last_login_at: string | null; balance: number }
interface TopPlayer { user_id: string; username: string; bets: number; wagered: number; won: number; net: number }
interface Live { generated_at: string; include_bots: boolean; kpis: Kpis; games: GameRow[]; hourly: HourPoint[]; recent_bets: BetRow[]; signups: Signup[]; top_players: TopPlayer[] }

const REFRESH_MS = 4000

const Kpi: React.FC<{ label: string; value: string; sub?: string; icon: React.ReactNode; tone?: string; onClick: () => void }> = ({ label, value, sub, icon, tone = 'text-white', onClick }) => (
  <button type="button" onClick={onClick} className="group rounded-2xl border border-dark-border bg-dark-card p-4 text-left transition hover:border-emerald-500/50 hover:bg-dark-elevated/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
    <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">{icon}{label}<ChevronRight className="ml-auto h-3.5 w-3.5 opacity-0 transition group-hover:opacity-100" /></p>
    <p className={`mt-2 font-mono text-xl font-black ${tone}`}>{value}</p>
    {sub && <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p>}
  </button>
)

const Panel: React.FC<{ title: string; hint?: string; children: React.ReactNode; right?: React.ReactNode }> = ({ title, hint, children, right }) => (
  <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
    <div className="mb-3 flex items-start justify-between gap-3">
      <div><h2 className="text-sm font-black text-white">{title}</h2>{hint && <p className="text-[11px] text-slate-500">{hint}</p>}</div>
      {right}
    </div>
    {children}
  </section>
)

const More: React.FC<{ onClick: () => void; children: React.ReactNode }> = ({ onClick, children }) => (
  <button type="button" onClick={onClick} className="flex shrink-0 items-center gap-0.5 text-xs text-emerald-300 hover:underline">{children}<ChevronRight className="h-3.5 w-3.5" /></button>
)

export const Dashboard: React.FC = () => {
  const [data, setData] = useState<Live | null>(null)
  const [includeBots, setIncludeBots] = useState(false)
  const [error, setError] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [loading, setLoading] = useState(false)
  const [stack, setStack] = useState<PanelTarget[]>([])
  const inflight = useRef(false)

  const open = useCallback((t: PanelTarget) => setStack((s) => [...s, t]), [])
  const close = useCallback(() => setStack([]), [])
  const back = useCallback(() => setStack((s) => s.slice(0, -1)), [])
  const list = (kind: string) => open({ type: 'list', kind })

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
  const games = (data?.games ?? []).filter((g) => g.game_id !== 'color')

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Live Operations</h1>
          <p className="flex items-center gap-2 text-xs text-slate-400">
            <span className={`h-2 w-2 rounded-full ${error ? 'bg-rose-500' : 'animate-pulse bg-emerald-500'}`} />
            {error ? 'Connection problem — retrying' : data ? `Real data · updated ${ago(data.generated_at, now)} · click anything for details` : 'Loading…'}
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
          {/* What is running right now */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {games.map((g) => (
              <button key={g.game_id} type="button" onClick={() => open({ type: 'game', id: g.game_id })}
                className="rounded-2xl border border-dark-border bg-dark-card p-3 text-left transition hover:border-emerald-500/50 hover:bg-dark-elevated/50">
                <p className="flex items-center justify-between text-xs font-black text-white">
                  {GAME_LABEL[g.game_id] ?? g.name}
                  {g.is_active ? <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />LIVE</span> : <span className="text-[10px] font-bold text-amber-300">PAUSED</span>}
                </p>
                <p className="mt-2 min-h-[2rem] text-[11px] leading-tight text-slate-300"><LiveStatus live={g.live} now={now} gameId={g.game_id} /></p>
                <p className="mt-1 text-[11px] text-slate-500">{g.live?.open_bets ?? 0} in play · {money(g.live?.open_stake ?? 0)}</p>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Players" value={k.players_total.toLocaleString()} sub={`+${k.signups_today} today · ${k.suspended} suspended`} icon={<Users className="h-4 w-4 text-emerald-400" />} onClick={() => list('players')} />
            <Kpi label="Active now" value={k.active_15m.toLocaleString()} sub={`last 15 min · ${k.active_24h} played in 24h`} icon={<Activity className="h-4 w-4 text-cyan-400" />} onClick={() => list('active_15m')} />
            <Kpi label="Bets today" value={k.bets_today.toLocaleString()} sub={`${k.players_today} players`} icon={<Gamepad2 className="h-4 w-4 text-purple-400" />} onClick={() => list('bets_today')} />
            <Kpi label="Wagered today" value={money(k.wagered_today)} sub={`paid ${money(k.paid_today)}`} icon={<IndianRupee className="h-4 w-4 text-sky-400" />} onClick={() => list('players_today')} />
            <Kpi label="House today" value={signed(k.house_today)} sub={`hold ${k.hold_pct_today}% · see winning bets`} tone={k.house_today >= 0 ? 'text-emerald-400' : 'text-rose-400'} icon={<Landmark className="h-4 w-4 text-emerald-400" />} onClick={() => list('won_today')} />
            <Kpi label="Player balances" value={money(k.player_balances)} sub={`${money(k.in_open_bets)} in open bets`} icon={<TrendingUp className="h-4 w-4 text-amber-400" />} onClick={() => list('balances')} />
            <Kpi label="New sign-ups" value={k.signups_today.toLocaleString()} sub="since midnight IST" icon={<UserPlus className="h-4 w-4 text-pink-400" />} onClick={() => list('signups_today')} />
            <Kpi label="Open tickets" value={k.open_tickets.toLocaleString()} sub="support queue" icon={<Ticket className="h-4 w-4 text-orange-400" />} onClick={() => list('tickets')} />
          </div>

          <Panel title="Last 24 hours — wagered vs paid" hint={`Hourly totals from real bets${data.include_bots ? ' (simulated players included)' : ''} · click an hour to see its bets`}
            right={<More onClick={() => list('open_bets')}>Bets in play</More>}>
            <HourlyFlowChart data={data.hourly} onSelect={(i) => open({ type: 'list', kind: 'hour', hour: data.hourly.length - 1 - i })} />
          </Panel>

          <Panel title="Games today" hint="Click a game for its live round, bets and results">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-2">Game</th><th className="py-2">Right now</th><th className="py-2 text-right">Bets</th><th className="py-2 text-right">Players</th><th className="py-2 text-right">Wagered</th><th className="py-2 text-right">Paid</th><th className="py-2 text-right">House</th><th className="py-2 text-right">Last bet</th><th /></tr></thead>
                <tbody>
                  {games.map((g) => (
                    <tr key={g.game_id} onClick={() => open({ type: 'game', id: g.game_id })} className="cursor-pointer border-t border-dark-border/50 hover:bg-dark-elevated/60">
                      <td className="py-2 font-bold text-white">{GAME_LABEL[g.game_id] ?? g.name}{!g.is_active && <span className="ml-1.5 text-amber-300">(paused)</span>}</td>
                      <td className="py-2 text-slate-300">{g.round_no ? <span className="mr-1 font-mono text-slate-500">#{g.round_no}</span> : null}<LiveStatus live={g.live} now={now} gameId={g.game_id} /></td>
                      <td className="py-2 text-right">{g.bets.toLocaleString()}</td>
                      <td className="py-2 text-right">{g.players.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono">{money(g.wagered)}</td>
                      <td className="py-2 text-right font-mono">{money(g.paid)}</td>
                      <td className={`py-2 text-right font-mono font-bold ${g.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{signed(g.house_net)}</td>
                      <td className="py-2 text-right text-slate-400">{ago(g.last_bet_at, now)}</td>
                      <td className="py-2 pl-2 text-slate-500"><ChevronRight className="h-4 w-4" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <Panel title="Latest bets" hint="Click a bet for its round and fairness proof · click a name for the player" right={<More onClick={() => list('bets_today')}>All today</More>}>
              <div className="max-h-[440px] overflow-auto">
                {data.recent_bets.length === 0 ? <p className="text-xs text-slate-400">No bets from real players yet.</p> : <BetsTable rows={data.recent_bets} now={now} onBet={(id) => open({ type: 'bet', id })} />}
              </div>
            </Panel>

            <div className="space-y-6">
              <Panel title="Top players today" right={<More onClick={() => list('players_today')}>Everyone who played</More>}>
                {data.top_players.length === 0 ? <p className="text-xs text-slate-400">No settled bets today.</p> : data.top_players.map((p, i) => (
                  <div key={p.user_id} className="flex items-center justify-between border-t border-dark-border/50 py-1.5 text-xs first:border-0">
                    <span className="text-slate-300"><span className="mr-2 text-slate-500">#{i + 1}</span><PlayerLink id={p.user_id} name={p.username} /> · {p.bets} bets · {money(p.wagered)}</span>
                    <span className={`font-mono font-bold ${p.net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{signed(p.net)}</span>
                  </div>
                ))}
              </Panel>
              <Panel title="Newest players" right={<More onClick={() => list('players')}>All players</More>}>
                {data.signups.length === 0 ? <p className="text-xs text-slate-400">No players yet.</p> : data.signups.map((s) => (
                  <div key={s.user_id} className="flex items-center justify-between border-t border-dark-border/50 py-1.5 text-xs first:border-0">
                    <span><PlayerLink id={s.user_id} name={s.username} /> <span className="text-slate-500">joined {ago(s.joined_at, now)}</span></span>
                    <span className="font-mono text-slate-300">{money(s.balance)}</span>
                  </div>
                ))}
              </Panel>
            </div>
          </div>
        </>
      )}

      <LiveDrawer target={stack[stack.length - 1] ?? null} includeBots={includeBots} now={now} onClose={close} onOpen={open} onBack={stack.length > 1 ? back : undefined} />
    </div>
  )
}
