import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Play, XCircle } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { getApiErrorMessage } from '../../../utils/apiError'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { showToast } from '../../../components/common/Toast'

// Validated categorical slots 1-2 (dark) on the #11151d card surface
const BLUE = '#3987e5'
const ORANGE = '#d95926'

type Status = 'pass' | 'warn' | 'fail'
interface Check { name: string; status: Status; detail: string }
interface Issue { round_no: number; round_id: string; entry_id: string | null; problem: string }
interface ReplayGame {
  rounds: number; hash_ok: number; outcome_ok: number; bets: number; settled_ok: number; open_in_finished: number
  wagered: number; paid: number; real_wagered: number; real_paid: number; issues: Issue[]; outcomes: Record<string, number>
  actual_hold_pct: number | null; expected_hold_pct: number | null; real_hold_pct: number | null
}
interface Report {
  generated_at: string; run_by: string | null; duration_s: number
  verdict: { status: Status; checks: Check[]; rounds_replayed: number; bets_replayed: number }
  replay: { days: number; max_rounds_per_game: number; games: Record<string, ReplayGame> }
  statistics: {
    wingo: { rounds: number; server_seed: string; number_counts: number[]; chi_square: { statistic: number; df: number; p_value: number }; picks: { pick: string; simulated_rtp_pct: number; theoretical_rtp_pct: number; z: number }[] }
    aviator: { rounds: number; server_seed: string; house_edge_bp: number; median_crash: number; instant_crash_pct: number; instant_crash_theoretical_pct: number; max_survival_gap_pp: number; survival: { multiplier: number; simulated_pct: number; theoretical_pct: number; z: number }[]; rtp: { cashout: number; simulated_rtp_pct: number; theoretical_rtp_pct: number }[] }
    mines: { layouts: number; mine_count: number; server_seed: string; house_edge_bp: number; tile_counts: number[]; chi_square: { statistic: number; df: number; p_value: number }; combos: { mines: number; tiles_opened: number; pays: number; win_chance_pct: number; simulated_win_pct: number; theoretical_rtp_pct: number; simulated_rtp_pct: number; z: number; sample: number }[] }
  }
}
interface HistoryRow { generated_at: string; run_by: string | null; status: Status; rounds: number; bets: number; hold_pct: number | null; failed_checks: string[] }

const GAME_LABEL: Record<string, string> = { aviator: 'Aviator', mines: 'Mines', teen_patti: 'Teen Patti', wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m' }
const card = 'rounded-2xl border border-dark-border bg-dark-card p-5'
const th = 'py-1.5 text-left font-semibold text-slate-400'

const StatusIcon: React.FC<{ s: Status; className?: string }> = ({ s, className = 'h-4 w-4' }) =>
  s === 'pass' ? <CheckCircle2 className={`${className} text-emerald-400`} /> : s === 'warn' ? <AlertTriangle className={`${className} text-amber-300`} /> : <XCircle className={`${className} text-rose-400`} />
const STATUS_TEXT: Record<Status, string> = { pass: 'Passed', warn: 'Passed with warnings', fail: 'Failed' }
const STATUS_TONE: Record<Status, string> = { pass: 'border-emerald-500/40 bg-emerald-500/10', warn: 'border-amber-500/40 bg-amber-500/10', fail: 'border-rose-500/40 bg-rose-500/10' }

const Z: React.FC<{ z: number }> = ({ z }) => <span className={Math.abs(z) < 3 ? 'text-slate-400' : Math.abs(z) < 4.5 ? 'text-amber-300' : 'text-rose-400'}>{z >= 0 ? '+' : ''}{z.toFixed(1)}σ</span>
const pct = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? '—' : `${v.toFixed(d)}%`)

/** WinGo: share of draws per number against the fair 10% line. */
const NumberChart: React.FC<{ counts: number[] }> = ({ counts }) => {
  const total = counts.reduce((a, b) => a + b, 0) || 1
  const shares = counts.map((c) => (c / total) * 100)
  const lo = Math.min(9.5, ...shares) - 0.1, hi = Math.max(10.5, ...shares) + 0.1
  const W = 520, H = 170, P = { t: 10, r: 60, b: 22, l: 40 }
  const bw = (W - P.l - P.r) / 10
  const y = (v: number) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Share of WinGo draws per number">
      {[lo, 10, hi].map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#252b37" /><text x={P.l - 6} y={y(t) + 3} fontSize={10} textAnchor="end" className="fill-slate-500">{t.toFixed(1)}%</text></g>)}
      {shares.map((s, n) => {
        const top = Math.min(y(s), y(10)), h = Math.max(2, Math.abs(y(s) - y(10)))
        return (
          <g key={n}>
            <rect x={P.l + n * bw + bw * 0.2} y={top} width={bw * 0.6} height={h} rx={3} fill={BLUE}><title>{`Number ${n}: ${counts[n].toLocaleString()} draws (${s.toFixed(3)}%)`}</title></rect>
            <text x={P.l + n * bw + bw / 2} y={H - 6} fontSize={10} textAnchor="middle" className="fill-slate-400">{n}</text>
          </g>
        )
      })}
      <line x1={P.l} x2={W - P.r} y1={y(10)} y2={y(10)} stroke="#94a3b8" strokeDasharray="5 4" />
      <text x={W - P.r + 6} y={y(10) + 3} fontSize={10} className="fill-slate-400">Fair 10%</text>
    </svg>
  )
}

/** Aviator: P(plane reaches x) simulated vs the closed-form formula. */
const SurvivalChart: React.FC<{ rows: Report['statistics']['aviator']['survival'] }> = ({ rows }) => {
  const W = 520, H = 190, P = { t: 12, r: 92, b: 24, l: 40 }
  const x = (i: number) => P.l + (i / (rows.length - 1)) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - v / 100) * (H - P.t - P.b)
  const path = (k: 'simulated_pct' | 'theoretical_pct') => rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r[k])}`).join(' ')
  const last = rows.length - 1
  return (
    <div>
      <div className="mb-1 flex gap-4 text-[11px] text-slate-300">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4" style={{ background: BLUE }} />Simulated</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: ORANGE }} />Formula</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Chance the plane reaches each multiplier">
        {[0, 50, 100].map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#252b37" /><text x={P.l - 6} y={y(t) + 3} fontSize={10} textAnchor="end" className="fill-slate-500">{t}%</text></g>)}
        {rows.map((r, i) => <text key={r.multiplier} x={x(i)} y={H - 6} fontSize={10} textAnchor="middle" className="fill-slate-500">{r.multiplier}x</text>)}
        <path d={path('theoretical_pct')} fill="none" stroke={ORANGE} strokeWidth={2} strokeDasharray="6 4" />
        <path d={path('simulated_pct')} fill="none" stroke={BLUE} strokeWidth={2} />
        {rows.map((r, i) => <circle key={i} cx={x(i)} cy={y(r.simulated_pct)} r={3.5} fill={BLUE} stroke="#11151d" strokeWidth={2}><title>{`${r.multiplier}x: simulated ${r.simulated_pct}% · formula ${r.theoretical_pct}%`}</title></circle>)}
        <text x={x(last) + 8} y={y(rows[last].simulated_pct) - 4} fontSize={10} className="fill-slate-300">Simulated</text>
      </svg>
    </div>
  )
}

/** Mines: how often each tile held a mine; every tile should be close to the same. */
const TileGrid: React.FC<{ counts: number[]; expected: number }> = ({ counts, expected }) => {
  const dev = counts.map((c) => (c - expected) / expected * 100)
  const maxDev = Math.max(1, ...dev.map((d) => Math.abs(d)))
  return (
    <div className="grid w-full max-w-[280px] grid-cols-5 gap-1">
      {counts.map((c, i) => (
        <div key={i} title={`Tile ${i + 1}: ${c.toLocaleString()} mines (${dev[i] >= 0 ? '+' : ''}${dev[i].toFixed(1)}% vs fair)`}
          className="flex aspect-square flex-col items-center justify-center rounded-md text-[10px]"
          style={{ background: `rgba(57,135,229,${0.15 + 0.45 * (1 - Math.abs(dev[i]) / maxDev)})` }}>
          <span className="font-mono font-bold text-white">{c}</span>
          <span className="text-slate-300">{dev[i] >= 0 ? '+' : ''}{dev[i].toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

export const BacktestTab: React.FC = () => {
  const [data, setData] = useState<{ report: Report | null; history: HistoryRow[] } | null>(null)
  const [days, setDays] = useState(30)
  const [maxRounds, setMaxRounds] = useState(3000)
  const [scale, setScale] = useState(1)
  const [running, setRunning] = useState(false)
  const [open, setOpen] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setData((await apiClient.get('/admin/backtest/latest')).data) } catch (e) { showToast({ title: 'Could not load backtest', message: getApiErrorMessage(e, 'Please try again.'), type: 'error' }) }
  }, [])
  useEffect(() => { void load() }, [load])

  const run = async () => {
    setRunning(true)
    try {
      await apiClient.post('/admin/backtest/run', { days, max_rounds: maxRounds, sim_scale: scale }, { timeout: 180000 })
      await load()
      showToast({ title: 'Backtest finished', message: 'The report below is updated.', type: 'success' })
    } catch (e) {
      showToast({ title: 'Backtest failed', message: getApiErrorMessage(e, 'Please try again.'), type: 'error' })
    } finally { setRunning(false) }
  }

  const r = data?.report
  const games = r ? Object.entries(r.replay.games) : []
  return (
    <div className="space-y-6">
      <section className={card}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <h2 className="text-sm font-black text-white">Algorithm backtest</h2>
            <p className="mt-1 text-[11px] text-slate-500">Replays every finished round from its revealed seed (hash, outcome and every payout), then runs large simulations of the same provably-fair code to test that numbers, crashes and mine layouts follow the published odds. Read-only: live games are not touched.</p>
          </div>
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="text-slate-400">Window<select value={days} onChange={(e) => setDays(Number(e.target.value))} className="mt-1 block rounded-xl border border-dark-border bg-dark-elevated px-2 py-1.5 text-slate-200">{[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select></label>
            <label className="text-slate-400">Rounds per game<select value={maxRounds} onChange={(e) => setMaxRounds(Number(e.target.value))} className="mt-1 block rounded-xl border border-dark-border bg-dark-elevated px-2 py-1.5 text-slate-200">{[500, 3000, 10000, 20000].map((d) => <option key={d} value={d}>{d.toLocaleString()}</option>)}</select></label>
            <label className="text-slate-400">Simulation size<select value={scale} onChange={(e) => setScale(Number(e.target.value))} className="mt-1 block rounded-xl border border-dark-border bg-dark-elevated px-2 py-1.5 text-slate-200">{[1, 2, 5].map((d) => <option key={d} value={d}>{d === 1 ? 'Standard' : `${d}× larger`}</option>)}</select></label>
            <button type="button" onClick={() => void run()} disabled={running} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 font-bold text-black hover:bg-emerald-400 disabled:opacity-50"><Play className="h-4 w-4" />{running ? 'Running… (up to a minute)' : 'Run full backtest'}</button>
          </div>
        </div>
      </section>

      {!data ? <p className="text-xs text-slate-400">Loading…</p> : !r ? <p className={`${card} text-sm text-slate-400`}>No backtest has been run yet. Start one above.</p> : (
        <>
          <section className={`rounded-2xl border p-5 ${STATUS_TONE[r.verdict.status]}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-lg font-black text-white"><StatusIcon s={r.verdict.status} className="h-6 w-6" />{STATUS_TEXT[r.verdict.status]}</h2>
              <p className="text-xs text-slate-300">{new Date(r.generated_at).toLocaleString()} · by {r.run_by ?? '—'} · {r.duration_s}s · {r.verdict.rounds_replayed.toLocaleString()} rounds and {r.verdict.bets_replayed.toLocaleString()} bets replayed</p>
            </div>
            <ul className="mt-4 grid gap-2 md:grid-cols-2">
              {r.verdict.checks.map((c) => (
                <li key={c.name} className="flex gap-2 rounded-xl bg-dark-card/60 p-3 text-xs"><StatusIcon s={c.status} /><div><p className="font-bold text-white">{c.name}</p><p className="text-slate-400">{c.detail}</p></div></li>
              ))}
            </ul>
          </section>

          <section className={card}>
            <h3 className="mb-1 text-sm font-black text-white">Historical replay (last {r.replay.days} days, up to {r.replay.max_rounds_per_game.toLocaleString()} rounds per game)</h3>
            <p className="mb-3 text-[11px] text-slate-500">Click a game to see its problems, if any.</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-xs">
                <thead><tr><th className={th} /><th className={th}>Game</th><th className={`${th} text-right`}>Rounds</th><th className={`${th} text-right`}>Seed hash ✓</th><th className={`${th} text-right`}>Outcome ✓</th><th className={`${th} text-right`}>Bets paid right</th><th className={`${th} text-right`}>Wagered</th><th className={`${th} text-right`}>Hold</th><th className={`${th} text-right`}>Expected</th><th className={`${th} text-right`}>Real players</th></tr></thead>
                <tbody>
                  {games.map(([id, g]) => {
                    const bad = g.issues.length > 0
                    return (
                      <React.Fragment key={id}>
                        <tr onClick={() => setOpen(open === id ? null : id)} className="cursor-pointer border-t border-dark-border/50 hover:bg-dark-elevated/50">
                          <td className="py-2 text-slate-500">{open === id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                          <td className="py-2 font-bold text-white">{GAME_LABEL[id] ?? id} {bad && <span className="ml-1 rounded bg-rose-500/20 px-1.5 text-[10px] text-rose-300">{g.issues.length} issue{g.issues.length > 1 ? 's' : ''}</span>}</td>
                          <td className="py-2 text-right">{g.rounds.toLocaleString()}</td>
                          <td className={`py-2 text-right ${g.hash_ok === g.rounds ? 'text-emerald-400' : 'text-rose-400'}`}>{g.hash_ok.toLocaleString()}</td>
                          <td className={`py-2 text-right ${g.outcome_ok === g.rounds ? 'text-emerald-400' : 'text-rose-400'}`}>{g.outcome_ok.toLocaleString()}</td>
                          <td className={`py-2 text-right ${g.settled_ok === g.bets ? 'text-emerald-400' : 'text-rose-400'}`}>{g.settled_ok.toLocaleString()} / {g.bets.toLocaleString()}</td>
                          <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.wagered)}</td>
                          <td className="py-2 text-right font-mono">{pct(g.actual_hold_pct)}</td>
                          <td className="py-2 text-right font-mono text-slate-300">{pct(g.expected_hold_pct)}</td>
                          <td className="py-2 text-right font-mono text-slate-300">{pct(g.real_hold_pct)}</td>
                        </tr>
                        {open === id && (
                          <tr><td colSpan={10} className="bg-dark-elevated/30 p-3">
                            <p className="mb-2 text-[11px] text-slate-400">Outcomes: {Object.entries(g.outcomes).map(([k, v]) => `${k} × ${v}`).join(' · ') || '—'}</p>
                            {g.issues.length === 0 ? <p className="flex items-center gap-1.5 text-xs text-emerald-300"><CheckCircle2 className="h-4 w-4" />Every round and bet matches the rules.</p> : (
                              <ul className="space-y-1 text-xs">{g.issues.map((i, k) => <li key={k} className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-rose-100">Round #{i.round_no}{i.entry_id ? <span className="font-mono text-rose-300/70"> · bet {i.entry_id.slice(0, 8)}</span> : null}: {i.problem}</li>)}</ul>
                            )}
                          </td></tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className={card}>
              <h3 className="text-sm font-black text-white">WinGo — {r.statistics.wingo.rounds.toLocaleString()} simulated draws</h3>
              <p className="mb-2 text-[11px] text-slate-500">Chi-square {r.statistics.wingo.chi_square.statistic} (df {r.statistics.wingo.chi_square.df}), p = {r.statistics.wingo.chi_square.p_value}. Above 0.001 means no detectable bias.</p>
              <NumberChart counts={r.statistics.wingo.number_counts} />
              <table className="mt-3 w-full text-xs">
                <thead><tr><th className={th}>Bet</th><th className={`${th} text-right`}>Simulated return</th><th className={`${th} text-right`}>Theory</th><th className={`${th} text-right`}>Deviation</th></tr></thead>
                <tbody>{r.statistics.wingo.picks.map((p) => <tr key={p.pick} className="border-t border-dark-border/50"><td className="py-1 text-slate-200">{p.pick}</td><td className="py-1 text-right font-mono">{p.simulated_rtp_pct.toFixed(2)}%</td><td className="py-1 text-right font-mono text-slate-400">{p.theoretical_rtp_pct.toFixed(2)}%</td><td className="py-1 text-right"><Z z={p.z} /></td></tr>)}</tbody>
              </table>
            </section>

            <section className={card}>
              <h3 className="text-sm font-black text-white">Aviator — {r.statistics.aviator.rounds.toLocaleString()} simulated flights</h3>
              <p className="mb-2 text-[11px] text-slate-500">House edge {(r.statistics.aviator.house_edge_bp / 100).toFixed(2)}% · median crash {r.statistics.aviator.median_crash.toFixed(2)}x · 1.00x crashes {r.statistics.aviator.instant_crash_pct}% (formula {r.statistics.aviator.instant_crash_theoretical_pct}%)</p>
              <SurvivalChart rows={r.statistics.aviator.survival} />
              <table className="mt-3 w-full text-xs">
                <thead><tr><th className={th}>Reaches</th><th className={`${th} text-right`}>Simulated</th><th className={`${th} text-right`}>Formula</th><th className={`${th} text-right`}>Deviation</th></tr></thead>
                <tbody>{r.statistics.aviator.survival.map((s) => <tr key={s.multiplier} className="border-t border-dark-border/50"><td className="py-1 text-slate-200">{s.multiplier}x</td><td className="py-1 text-right font-mono">{s.simulated_pct.toFixed(2)}%</td><td className="py-1 text-right font-mono text-slate-400">{s.theoretical_pct.toFixed(2)}%</td><td className="py-1 text-right"><Z z={s.z} /></td></tr>)}</tbody>
              </table>
              <p className="mt-3 text-[11px] text-slate-400">Player return when always cashing out at: {r.statistics.aviator.rtp.map((x) => `${x.cashout}x → ${x.simulated_rtp_pct}% (theory ${x.theoretical_rtp_pct}%)`).join(' · ')}</p>
            </section>
          </div>

          <section className={card}>
            <h3 className="text-sm font-black text-white">Mines — {r.statistics.mines.layouts.toLocaleString()} simulated boards</h3>
            <p className="mb-3 text-[11px] text-slate-500">Board with {r.statistics.mines.mine_count} mines: how often each tile held a mine. Chi-square p = {r.statistics.mines.chi_square.p_value} (above 0.001 = no tile is favoured). House edge {(r.statistics.mines.house_edge_bp / 100).toFixed(2)}%.</p>
            <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
              <TileGrid counts={r.statistics.mines.tile_counts} expected={r.statistics.mines.layouts * r.statistics.mines.mine_count / 25} />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-xs">
                  <thead><tr><th className={th}>Mines</th><th className={th}>Tiles opened</th><th className={`${th} text-right`}>Pays</th><th className={`${th} text-right`}>Win chance</th><th className={`${th} text-right`}>Simulated</th><th className={`${th} text-right`}>Return (theory)</th><th className={`${th} text-right`}>Deviation</th></tr></thead>
                  <tbody>{r.statistics.mines.combos.map((c) => <tr key={`${c.mines}-${c.tiles_opened}`} className="border-t border-dark-border/50"><td className="py-1">{c.mines}</td><td className="py-1">{c.tiles_opened}</td><td className="py-1 text-right font-mono">{c.pays.toFixed(2)}x</td><td className="py-1 text-right font-mono text-slate-400">{c.win_chance_pct.toFixed(2)}%</td><td className="py-1 text-right font-mono">{c.simulated_win_pct.toFixed(2)}%</td><td className="py-1 text-right font-mono text-slate-400">{c.theoretical_rtp_pct.toFixed(2)}%</td><td className="py-1 text-right"><Z z={c.z} /></td></tr>)}</tbody>
                </table>
                <p className="mt-2 text-[11px] text-slate-500">σ = standard errors from theory. Within ±3σ is ordinary chance; beyond ±4.5σ would point to a fault.</p>
              </div>
            </div>
          </section>

          <section className={card}>
            <h3 className="mb-2 text-sm font-black text-white">Earlier runs</h3>
            <table className="w-full text-xs">
              <thead><tr><th className={th}>When</th><th className={th}>By</th><th className={th}>Result</th><th className={`${th} text-right`}>Rounds</th><th className={`${th} text-right`}>Bets</th><th className={`${th} text-right`}>Hold</th><th className={th}>Not passed</th></tr></thead>
              <tbody>{data.history.map((h) => <tr key={h.generated_at} className="border-t border-dark-border/50"><td className="py-1 text-slate-300">{new Date(h.generated_at).toLocaleString()}</td><td className="py-1 text-slate-400">{h.run_by ?? '—'}</td><td className="py-1"><span className="flex items-center gap-1"><StatusIcon s={h.status} className="h-3.5 w-3.5" />{STATUS_TEXT[h.status]}</span></td><td className="py-1 text-right">{h.rounds.toLocaleString()}</td><td className="py-1 text-right">{h.bets.toLocaleString()}</td><td className="py-1 text-right font-mono">{pct(h.hold_pct)}</td><td className="py-1 text-slate-400">{h.failed_checks.join(', ') || '—'}</td></tr>)}</tbody>
            </table>
          </section>
          <p className="break-all text-[11px] text-slate-500">Simulation seeds (reproducible): WinGo {r.statistics.wingo.server_seed} · Aviator {r.statistics.aviator.server_seed} · Mines {r.statistics.mines.server_seed} · client seed "backtest", nonce 0…n−1.</p>
        </>
      )}
    </div>
  )
}
