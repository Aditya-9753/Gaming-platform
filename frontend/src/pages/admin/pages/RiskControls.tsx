import React, { useCallback, useEffect, useState } from 'react'
import { Gauge, Play, ShieldCheck, ShieldOff } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { getApiErrorMessage } from '../../../utils/apiError'
import { formatPaiseToRupee } from '../../../utils/formatters'

interface Control {
  status: 'ON' | 'OFF'
  target_hold_pct_bp: number
  max_round_pool_paise: number
  max_player_round_paise: number
}
interface ControlsResponse {
  families: Record<string, Control>
  matrix: Array<{ game_id: string; family: string; status: string }>
  notes: Record<string, string>
}
interface BacktestGame {
  family: string | null
  status: string
  settled_entries: number
  wagered_paise: number
  hold_pct: number | null
  target_hold_pct: number | null
  delta_pct: number | null
  verdict: string
}
interface BacktestReport {
  window_days: number
  games: Record<string, BacktestGame>
  totals: { wagered_paise: number; hold_pct: number | null; settled_entries: number }
  control_impact: {
    games: Record<string, { rounds_over_pool_cap: number; player_cap_breaches: number; would_decline_paise: number }>
  }
}

const FAMILY_LABEL: Record<string, string> = { wingo: 'WinGo (all modes)', aviator: 'Aviator', mines: 'Mines' }
const GAME_LABEL: Record<string, string> = {
  wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m', aviator: 'Aviator', mines: 'Mines',
}
const VERDICT: Record<string, { label: string; tone: string }> = {
  on_target: { label: 'On target', tone: 'text-emerald-400' },
  above_target: { label: 'Above target', tone: 'text-sky-400' },
  below_target: { label: 'Below target', tone: 'text-rose-400' },
  no_data: { label: 'No data', tone: 'text-slate-500' },
}

type Draft = { round: string; player: string; target: string }

/** Super-admin risk controls: per-game ON/OFF exposure ceilings + yield backtest. */
export const RiskControls: React.FC = () => {
  const [families, setFamilies] = useState<Record<string, Control>>({})
  const [matrix, setMatrix] = useState<ControlsResponse['matrix']>([])
  const [draft, setDraft] = useState<Record<string, Draft>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [days, setDays] = useState(30)
  const [report, setReport] = useState<BacktestReport | null>(null)
  const [running, setRunning] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await apiClient.get<ControlsResponse>('/admin/risk/controls')
      setFamilies(data.families)
      setMatrix(data.matrix)
      setDraft(Object.fromEntries(Object.entries(data.families).map(([f, c]) => [f, {
        round: (c.max_round_pool_paise / 100).toString(),
        player: (c.max_player_round_paise / 100).toString(),
        target: (c.target_hold_pct_bp / 100).toString(),
      }])))
    } catch (error) {
      showToast({ title: 'Could not load risk controls', message: getApiErrorMessage(error, 'Super admin only.'), type: 'error' })
    }
  }, [])

  const loadReport = useCallback(async () => {
    try {
      const { data } = await apiClient.get<{ report: BacktestReport | null }>('/admin/risk/backtest/latest')
      if (data.report) setReport(data.report)
    } catch { /* no report yet */ }
  }, [])

  useEffect(() => { void load(); void loadReport() }, [load, loadReport])

  const toggle = async (family: string, next: 'ON' | 'OFF') => {
    setBusy(family)
    try {
      await apiClient.post('/admin/risk/controls/toggle', { game: family, status: next })
      await load()
      showToast({ title: `${FAMILY_LABEL[family] ?? family} → ${next}`, type: 'success' })
    } catch (error) {
      showToast({ title: 'Could not change switch', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    } finally {
      setBusy(null)
    }
  }

  const save = async (family: string) => {
    const d = draft[family]
    if (!d) return
    setBusy(family)
    try {
      await apiClient.post('/admin/risk/controls/update', {
        family,
        changes: {
          target_hold_pct_bp: Math.round(Number(d.target) * 100),
          max_round_pool_paise: Math.round(Number(d.round) * 100),
          max_player_round_paise: Math.round(Number(d.player) * 100),
        },
      })
      await load()
      showToast({ title: 'Ceilings saved', type: 'success' })
    } catch (error) {
      showToast({ title: 'Could not save', message: getApiErrorMessage(error, 'Check the values.'), type: 'error' })
    } finally {
      setBusy(null)
    }
  }

  const runBacktest = async () => {
    setRunning(true)
    try {
      const { data } = await apiClient.post<BacktestReport>('/admin/risk/backtest', { days, max_rounds: 2000 }, { timeout: 120000 })
      setReport(data)
      showToast({ title: 'Backtest finished', type: 'success' })
    } catch (error) {
      showToast({ title: 'Backtest failed', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Risk Controls</h1>
        <p className="text-xs text-slate-400">
          Per-game exposure ceilings and yield backtest. The switch limits how much can be staked — it changes
          <span className="font-bold text-slate-300"> what bets are accepted</span>, never the round result. Outcomes stay provably fair.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {Object.entries(families).map(([family, control]) => {
          const d = draft[family] ?? { round: '0', player: '0', target: '0' }
          const on = control.status === 'ON'
          return (
            <section key={family} className={`rounded-2xl border bg-dark-card p-5 ${on ? 'border-emerald-500/40' : 'border-dark-border'}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-black text-white">{FAMILY_LABEL[family] ?? family}</h2>
                <button
                  type="button"
                  disabled={busy === family}
                  onClick={() => void toggle(family, on ? 'OFF' : 'ON')}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-black transition ${on ? 'bg-emerald-500 text-dark-bg' : 'bg-dark-elevated text-slate-400'}`}
                >
                  {on ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldOff className="h-3.5 w-3.5" />} {control.status}
                </button>
              </div>

              <div className="mt-4 space-y-2 text-xs">
                <label className="block">
                  <span className="text-slate-400">Round stake cap (₹, 0 = off)</span>
                  <input type="number" min="0" value={d.round}
                    onChange={(e) => setDraft((s) => ({ ...s, [family]: { ...d, round: e.target.value } }))}
                    className="mt-1 w-full rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 font-mono text-white" />
                </label>
                <label className="block">
                  <span className="text-slate-400">Per-player cap (₹, 0 = off)</span>
                  <input type="number" min="0" value={d.player}
                    onChange={(e) => setDraft((s) => ({ ...s, [family]: { ...d, player: e.target.value } }))}
                    className="mt-1 w-full rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 font-mono text-white" />
                </label>
                <label className="block">
                  <span className="text-slate-400">Target hold (%)</span>
                  <input type="number" min="0" max="99.99" step="0.01" value={d.target}
                    onChange={(e) => setDraft((s) => ({ ...s, [family]: { ...d, target: e.target.value } }))}
                    className="mt-1 w-full rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 font-mono text-white" />
                </label>
              </div>
              <button type="button" disabled={busy === family} onClick={() => void save(family)}
                className="mt-4 w-full rounded-xl bg-purple-500 px-4 py-2 text-xs font-black text-white disabled:opacity-50">
                Save
              </button>
            </section>
          )
        })}
      </div>

      <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-black text-white"><Gauge className="h-4 w-4 text-purple-400" /> Yield backtest</h2>
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-full border border-dark-border p-0.5 text-xs font-bold">
              {[7, 30, 90, 365].map((dd) => (
                <button key={dd} type="button" onClick={() => setDays(dd)}
                  className={`rounded-full px-3 py-1 ${days === dd ? 'bg-emerald-500 text-dark-bg' : 'text-slate-400'}`}>{dd}d</button>
              ))}
            </div>
            <button type="button" disabled={running} onClick={() => void runBacktest()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-purple-500 px-4 py-2 text-xs font-black text-white disabled:opacity-50">
              <Play className="h-3.5 w-3.5" /> {running ? 'Running…' : 'Run'}
            </button>
          </div>
        </div>

        {!report ? <p className="mt-4 text-sm text-slate-400">No backtest yet — run one.</p> : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400">
                <th className="py-1.5">Game</th><th className="py-1.5 text-right">Bets</th><th className="py-1.5 text-right">Wagered</th>
                <th className="py-1.5 text-right">Hold %</th><th className="py-1.5 text-right">Target %</th><th className="py-1.5 text-right">Verdict</th>
                <th className="py-1.5 text-right">Declined (₹)</th>
              </tr></thead>
              <tbody>
                {Object.entries(report.games).map(([gameId, g]) => {
                  const impact = report.control_impact.games[gameId]
                  const v = VERDICT[g.verdict] ?? VERDICT.no_data
                  return (
                    <tr key={gameId} className="border-t border-dark-border/50">
                      <td className="py-2 font-bold text-white">{GAME_LABEL[gameId] ?? gameId}</td>
                      <td className="py-2 text-right">{g.settled_entries.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.wagered_paise)}</td>
                      <td className="py-2 text-right font-mono">{g.hold_pct == null ? '—' : `${g.hold_pct}%`}</td>
                      <td className="py-2 text-right font-mono text-slate-400">{g.target_hold_pct == null ? '—' : `${g.target_hold_pct}%`}</td>
                      <td className={`py-2 text-right font-bold ${v.tone}`}>{v.label}</td>
                      <td className="py-2 text-right font-mono text-slate-400">{impact ? formatPaiseToRupee(impact.would_decline_paise) : '—'}</td>
                    </tr>
                  )
                })}
                {Object.keys(report.games).length === 0 && <tr><td colSpan={7} className="py-4 text-center text-slate-500">No settled bets in this window.</td></tr>}
              </tbody>
            </table>
            <p className="mt-3 text-[11px] text-slate-500">
              Window {report.window_days}d · total wagered {formatPaiseToRupee(report.totals.wagered_paise)} · overall hold {report.totals.hold_pct == null ? '—' : `${report.totals.hold_pct}%`}.
              “Declined” estimates the stake the current ON ceilings would have turned away; nothing here affects a round outcome.
            </p>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
        <h2 className="mb-3 text-sm font-black text-white">Control matrix</h2>
        <div className="flex flex-wrap gap-2 text-xs">
          {matrix.map((row) => (
            <span key={row.game_id} className="rounded-full border border-dark-border bg-dark-elevated px-3 py-1.5">
              <span className="text-white">{GAME_LABEL[row.game_id] ?? row.game_id}</span>
              <span className={`ml-2 font-black ${row.status === 'ON' ? 'text-emerald-400' : 'text-slate-500'}`}>{row.status}</span>
            </span>
          ))}
        </div>
      </section>
    </div>
  )
}