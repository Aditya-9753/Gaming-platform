import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, FlaskConical, KeyRound, Lock, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { getApiErrorMessage } from '../../../utils/apiError'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { showToast } from '../../../components/common/Toast'
import { BacktestTab } from '../components/BacktestReport'

type Tab = 'backtest' | 'hold' | 'integrity' | 'seed'

// Validated categorical slot 1 (dark) on the #11151d card surface
const SERIES = '#3987e5'

const card = 'rounded-2xl border border-dark-border bg-dark-card p-5'
const btn = 'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition disabled:opacity-50'
const input = 'w-full rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none'

const errorToast = (title: string, e: unknown) => showToast({ title, message: getApiErrorMessage(e, 'Please try again.'), type: 'error' })

// ------------------------------------------------------------------ Hold analyzer
interface HoldGame { game_id: string; name: string; bets: number; wagered: number; paid: number; house: number; actual_hold_pct: number; expected_hold_pct: number | null; band_pct: number | null; within_band: boolean | null; basis: string }
interface HoldReport { days: number; games: HoldGame[]; total: { bets: number; wagered: number; paid: number; house: number; actual_hold_pct: number }; note: string }
interface SimResult {
  game: string; rounds: number; server_seed: string; client_seed: string; simulated_hold_pct: number; expected_hold_pct: number
  series: { round: number; hold_pct: number }[]; number_counts?: number[]; win_rate_pct?: number; multiplier?: number
  bet_mix?: { type: string; value: string; share: number }[]
}

const WINGO_KEYS: [string, string, number][] = [
  ['NUMBER', 'Exact number', 9], ['GREEN', 'Green / Red', 2], ['COLOR_HALF', 'Green/Red on 5 or 0', 1.5], ['VIOLET', 'Violet', 4.5], ['SIZE', 'Big / Small', 1.96],
]

/** Cumulative hold over the simulated rounds, with the expected hold as a labelled reference line. */
const HoldLine: React.FC<{ sim: SimResult }> = ({ sim }) => {
  const [hover, setHover] = useState<number | null>(null)
  const W = 640, H = 200, P = { t: 14, r: 96, b: 24, l: 48 }
  const pts = sim.series
  const vals = [...pts.map((p) => p.hold_pct), sim.expected_hold_pct]
  const lo = Math.floor(Math.min(...vals) - 1), hi = Math.ceil(Math.max(...vals) + 1)
  const x = (i: number) => P.l + (pts.length < 2 ? 0 : (i / (pts.length - 1)) * (W - P.l - P.r))
  const y = (v: number) => P.t + (1 - (v - lo) / (hi - lo || 1)) * (H - P.t - P.b)
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.hold_pct).toFixed(1)}`).join(' ')
  const ticks = [lo, (lo + hi) / 2, hi]
  const last = pts.length - 1
  if (pts.length === 0) return null
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Simulated house hold over rounds">
        {ticks.map((t) => (
          <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#252b37" /><text x={P.l - 6} y={y(t) + 3} textAnchor="end" fontSize={10} className="fill-slate-500">{t.toFixed(1)}%</text></g>
        ))}
        <line x1={P.l} x2={W - P.r} y1={y(sim.expected_hold_pct)} y2={y(sim.expected_hold_pct)} stroke="#94a3b8" strokeDasharray="5 4" />
        <text x={W - P.r + 6} y={y(sim.expected_hold_pct) + 3} fontSize={10} className="fill-slate-400">Expected {sim.expected_hold_pct.toFixed(2)}%</text>
        <path d={path} fill="none" stroke={SERIES} strokeWidth={2} strokeLinejoin="round" />
        <circle cx={x(last)} cy={y(pts[last].hold_pct)} r={4} fill={SERIES} stroke="#11151d" strokeWidth={2} />
        <text x={W - P.r + 6} y={y(pts[last].hold_pct) + (Math.abs(y(pts[last].hold_pct) - y(sim.expected_hold_pct)) < 12 ? 14 : 3)} fontSize={10} className="fill-slate-300">Simulated {pts[last].hold_pct.toFixed(2)}%</text>
        <text x={P.l} y={H - 6} fontSize={10} className="fill-slate-500">1</text>
        <text x={W - P.r} y={H - 6} fontSize={10} textAnchor="end" className="fill-slate-500">{sim.rounds.toLocaleString()} rounds</text>
        {hover !== null && <><line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#64748b" strokeDasharray="3 3" /><circle cx={x(hover)} cy={y(pts[hover].hold_pct)} r={4} fill={SERIES} stroke="#11151d" strokeWidth={2} /></>}
        {pts.map((_p, i) => (
          <rect key={i} x={x(i) - (W - P.l - P.r) / pts.length / 2} y={P.t} width={(W - P.l - P.r) / pts.length} height={H - P.t - P.b} fill="transparent" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
        ))}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute top-0 rounded-lg border border-dark-border bg-dark-elevated px-3 py-1.5 text-[11px] text-slate-300 shadow-xl" style={{ left: `${Math.min(68, (x(hover) / W) * 100)}%` }}>
          After <b className="text-white">{pts[hover].round.toLocaleString()}</b> rounds: hold <b className="font-mono text-white">{pts[hover].hold_pct.toFixed(2)}%</b>
        </div>
      )}
    </div>
  )
}

/** How often each WinGo number came up: should be flat (each about 10%). */
const NumberBars: React.FC<{ counts: number[] }> = ({ counts }) => {
  const total = counts.reduce((a, b) => a + b, 0) || 1
  const max = Math.max(...counts.map((c) => c / total), 0.12)
  return (
    <div>
      <div className="flex h-28 items-end gap-1.5" role="img" aria-label="Share of draws per number">
        {counts.map((c, n) => (
          <div key={n} className="group relative flex h-full flex-1 flex-col justify-end">
            <div className="rounded-t" style={{ height: `${(c / total / max) * 100}%`, background: SERIES }} title={`${n}: ${c.toLocaleString()} draws (${(c / total * 100).toFixed(2)}%)`} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1.5 text-center text-[10px] text-slate-500">{counts.map((c, n) => <span key={n} className="flex-1">{n}<br />{(c / total * 100).toFixed(1)}%</span>)}</div>
    </div>
  )
}

const HoldTab: React.FC = () => {
  const [days, setDays] = useState(7)
  const [bots, setBots] = useState(false)
  const [report, setReport] = useState<HoldReport | null>(null)
  const [game, setGame] = useState<'wingo' | 'aviator' | 'mines'>('wingo')
  const [rounds, setRounds] = useState(20000)
  const [payouts, setPayouts] = useState<Record<string, number>>(Object.fromEntries(WINGO_KEYS.map(([k, , d]) => [k, d])))
  const [useMix, setUseMix] = useState(true)
  const [edge, setEdge] = useState(3)
  const [cashout, setCashout] = useState(2)
  const [mines, setMines] = useState(3)
  const [reveal, setReveal] = useState(3)
  const [sim, setSim] = useState<SimResult | null>(null)
  const [running, setRunning] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await apiClient.get<HoldReport>('/admin/hold/analysis', { params: { days, include_bots: bots } })
      setReport(data)
    } catch (e) { errorToast('Could not load hold analysis', e) }
  }, [days, bots])
  useEffect(() => { void load() }, [load])

  const simulate = async () => {
    setRunning(true)
    try {
      const body: Record<string, unknown> = { game, rounds }
      if (game === 'wingo') Object.assign(body, { payouts, use_bet_mix: useMix })
      if (game !== 'wingo') body.house_edge_bp = Math.round(edge * 100)
      if (game === 'aviator') body.cashout_at = cashout
      if (game === 'mines') Object.assign(body, { mine_count: mines, reveal })
      const { data } = await apiClient.post<SimResult>('/admin/hold/simulate', body)
      setSim(data)
    } catch (e) { errorToast('Simulation failed', e) } finally { setRunning(false) }
  }

  return (
    <div className="space-y-6">
      <section className={card}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-black text-white">Actual vs expected hold</h2>
            <p className="text-[11px] text-slate-500">What the house kept from settled bets, next to what the payout table and house edge predict. {report?.note}</p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-xl border border-dark-border bg-dark-elevated px-2 py-1.5 text-slate-200">
              {[1, 7, 30, 90].map((d) => <option key={d} value={d}>Last {d} day{d > 1 ? 's' : ''}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-slate-300"><input type="checkbox" checked={bots} onChange={(e) => setBots(e.target.checked)} />Include simulated players</label>
            <button type="button" onClick={() => void load()} aria-label="Refresh" className="rounded-lg p-1.5 text-slate-400 hover:text-white"><RefreshCw className="h-4 w-4" /></button>
          </div>
        </div>
        {!report ? <p className="text-xs text-slate-400">Loading…</p> : report.games.length === 0 ? <p className="text-xs text-slate-400">No settled bets in this period.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-xs">
              <thead><tr className="text-left text-slate-400"><th className="py-2">Game</th><th className="py-2 text-right">Bets</th><th className="py-2 text-right">Wagered</th><th className="py-2 text-right">Paid</th><th className="py-2 text-right">Actual hold</th><th className="py-2 text-right">Expected</th><th className="py-2 text-right">95% range</th><th className="py-2 pl-3">Basis</th></tr></thead>
              <tbody>
                {report.games.map((g) => (
                  <tr key={g.game_id} className="border-t border-dark-border/50">
                    <td className="py-2 font-bold text-white">{g.name}</td>
                    <td className="py-2 text-right">{g.bets.toLocaleString()}</td>
                    <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.wagered)}</td>
                    <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.paid)}</td>
                    <td className={`py-2 text-right font-mono font-bold ${g.actual_hold_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{g.actual_hold_pct.toFixed(2)}%</td>
                    <td className="py-2 text-right font-mono text-slate-200">{g.expected_hold_pct !== null ? `${g.expected_hold_pct.toFixed(2)}%` : '—'}</td>
                    <td className="py-2 text-right text-slate-400">
                      {g.band_pct !== null && g.expected_hold_pct !== null ? <>±{g.band_pct.toFixed(1)}% {g.within_band ? <span className="text-emerald-400">✓ normal</span> : <span className="text-amber-300">⚠ unusual</span>}</> : '—'}
                    </td>
                    <td className="py-2 pl-3 text-slate-500">{g.basis}</td>
                  </tr>
                ))}
                <tr className="border-t border-dark-border font-bold">
                  <td className="py-2 text-white">All games</td><td className="py-2 text-right">{report.total.bets.toLocaleString()}</td>
                  <td className="py-2 text-right font-mono">{formatPaiseToRupee(report.total.wagered)}</td><td className="py-2 text-right font-mono">{formatPaiseToRupee(report.total.paid)}</td>
                  <td className={`py-2 text-right font-mono ${report.total.actual_hold_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{report.total.actual_hold_pct.toFixed(2)}%</td><td colSpan={3} />
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={card}>
        <h2 className="flex items-center gap-2 text-sm font-black text-white"><FlaskConical className="h-4 w-4 text-sky-400" />What-if simulator</h2>
        <p className="mb-4 text-[11px] text-slate-500">Runs the real provably-fair code with a fresh random seed. It changes nothing in live games. To apply a new payout or edge for everyone, change it in <Link to="/admin/game-settings" className="text-emerald-300 hover:underline">Game Settings</Link>.</p>
        <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-3 gap-1 rounded-xl bg-dark-elevated p-1">
              {(['wingo', 'aviator', 'mines'] as const).map((g) => (
                <button key={g} type="button" onClick={() => { setGame(g); setSim(null) }} className={`rounded-lg py-1.5 font-bold capitalize ${game === g ? 'bg-emerald-500 text-black' : 'text-slate-300'}`}>{g === 'wingo' ? 'WinGo' : g}</button>
              ))}
            </div>
            <label className="block text-slate-400">Rounds<input type="number" min={100} max={100000} step={1000} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} className={input} /></label>
            {game === 'wingo' && (
              <>
                {WINGO_KEYS.map(([k, label]) => (
                  <label key={k} className="flex items-center justify-between gap-3 text-slate-400">{label}<input type="number" step={0.01} min={1} max={100} value={payouts[k]} onChange={(e) => setPayouts({ ...payouts, [k]: Number(e.target.value) })} className={`${input} w-24 text-right`} /></label>
                ))}
                <label className="flex items-center gap-2 text-slate-300"><input type="checkbox" checked={useMix} onChange={(e) => setUseMix(e.target.checked)} />Weight picks like real players (last 30 days)</label>
              </>
            )}
            {game !== 'wingo' && <label className="block text-slate-400">House edge %<input type="number" step={0.1} min={0} max={50} value={edge} onChange={(e) => setEdge(Number(e.target.value))} className={input} /></label>}
            {game === 'aviator' && <label className="block text-slate-400">Player cashes out at (x)<input type="number" step={0.1} min={1.01} max={100} value={cashout} onChange={(e) => setCashout(Number(e.target.value))} className={input} /></label>}
            {game === 'mines' && (
              <div className="grid grid-cols-2 gap-2">
                <label className="block text-slate-400">Mines<input type="number" min={1} max={24} value={mines} onChange={(e) => setMines(Number(e.target.value))} className={input} /></label>
                <label className="block text-slate-400">Tiles opened<input type="number" min={1} max={24} value={reveal} onChange={(e) => setReveal(Number(e.target.value))} className={input} /></label>
              </div>
            )}
            <button type="button" onClick={() => void simulate()} disabled={running} className={`${btn} w-full justify-center bg-emerald-500 text-black hover:bg-emerald-400`}>{running ? 'Simulating…' : 'Run simulation'}</button>
          </div>
          <div className="min-w-0 space-y-4">
            {!sim ? <p className="rounded-xl bg-dark-elevated/40 p-6 text-center text-xs text-slate-400">Pick settings and run a simulation.</p> : (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
                  <div className="rounded-xl bg-dark-elevated/50 p-3"><p className="text-slate-400">Simulated hold</p><p className="font-mono text-lg font-black text-white">{sim.simulated_hold_pct.toFixed(2)}%</p></div>
                  <div className="rounded-xl bg-dark-elevated/50 p-3"><p className="text-slate-400">Expected hold</p><p className="font-mono text-lg font-black text-white">{sim.expected_hold_pct.toFixed(2)}%</p></div>
                  <div className="rounded-xl bg-dark-elevated/50 p-3"><p className="text-slate-400">Player return</p><p className="font-mono text-lg font-black text-white">{(100 - sim.expected_hold_pct).toFixed(2)}%</p></div>
                  {sim.win_rate_pct !== undefined && <div className="rounded-xl bg-dark-elevated/50 p-3"><p className="text-slate-400">Player win rate</p><p className="font-mono text-lg font-black text-white">{sim.win_rate_pct.toFixed(2)}%</p>{sim.multiplier && <p className="text-slate-500">pays {sim.multiplier.toFixed(2)}x</p>}</div>}
                </div>
                <HoldLine sim={sim} />
                {sim.number_counts && <div><p className="mb-2 text-xs font-bold text-slate-300">Numbers drawn (fair RNG: each about 10%)</p><NumberBars counts={sim.number_counts} /></div>}
                <p className="break-all text-[11px] text-slate-500">Reproducible: server seed <span className="font-mono text-slate-400">{sim.server_seed}</span>, client seed <span className="font-mono">{sim.client_seed}</span>, nonce 0…{sim.rounds - 1}.</p>
              </>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

// ------------------------------------------------------------------ Integrity
interface IntegrityStatus { configured: boolean; algorithm: string; key_id: string | null; tables: Record<'ledger' | 'audit', { total: number; sealed: number; unsealed: number }> }
interface VerifyResult { kind: string; checked: number; ok: number; tampered: number; unsealed: number; tampered_rows: { id: string; created_at: string | null; label: string; reason: string; changes?: Record<string, { sealed: unknown; now: unknown }> }[] }

const TABLE_LABEL = { ledger: 'Wallet ledger', audit: 'Admin audit log' }

const IntegrityTab: React.FC = () => {
  const [status, setStatus] = useState<IntegrityStatus | null>(null)
  const [results, setResults] = useState<Partial<Record<'ledger' | 'audit', VerifyResult>>>({})
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    try { setStatus((await apiClient.get<IntegrityStatus>('/admin/integrity/status')).data) } catch (e) { errorToast('Could not load status', e) }
  }, [])
  useEffect(() => { void load() }, [load])

  const verify = async (kind: 'ledger' | 'audit') => {
    setBusy(`v-${kind}`)
    try {
      const { data } = await apiClient.post<VerifyResult>('/admin/integrity/verify', { kind, limit: 5000 })
      setResults((r) => ({ ...r, [kind]: data }))
      showToast({ title: data.tampered ? 'Tampering found' : 'All checked rows are intact', message: `${data.ok} ok · ${data.tampered} tampered · ${data.unsealed} unsealed`, type: data.tampered ? 'error' : 'success' })
    } catch (e) { errorToast('Verification failed', e) } finally { setBusy('') }
  }
  const sealOld = async (kind: 'ledger' | 'audit') => {
    if (!window.confirm('Seal the older rows as they are now? Only do this if you trust their current values.')) return
    setBusy(`s-${kind}`)
    try {
      const { data } = await apiClient.post<{ sealed: number }>('/admin/integrity/seal-existing', { kind })
      showToast({ title: 'Rows sealed', message: `${data.sealed} rows sealed`, type: 'success' })
      await load()
    } catch (e) { errorToast('Sealing failed', e) } finally { setBusy('') }
  }

  if (!status) return <p className="text-xs text-slate-400">Loading…</p>
  return (
    <div className="space-y-6">
      <section className={card}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-black text-white"><Lock className="h-4 w-4 text-emerald-400" />Tamper-evident ledger</h2>
            <p className="mt-1 max-w-2xl text-[11px] text-slate-500">Every wallet transaction and admin action is sealed with {status.algorithm}. If anyone edits a row directly in the database, its seal no longer matches and it shows up here as tampered. The key is kept only in the server environment.</p>
          </div>
          {status.configured
            ? <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-bold text-emerald-300"><ShieldCheck className="h-4 w-4" />Active · key {status.key_id}</span>
            : <span className="flex items-center gap-1.5 rounded-full bg-amber-500/15 px-3 py-1 text-xs font-bold text-amber-300"><ShieldAlert className="h-4 w-4" />Not configured</span>}
        </div>
        {!status.configured && <p className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">Set <span className="font-mono">AUDIT_ENCRYPTION_KEY</span> (64 hex characters) on the server to start sealing rows.</p>}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {(['ledger', 'audit'] as const).map((kind) => {
          const t = status.tables[kind]
          const r = results[kind]
          return (
            <section key={kind} className={card}>
              <h3 className="text-sm font-black text-white">{TABLE_LABEL[kind]}</h3>
              <p className="mt-1 text-xs text-slate-400">{t.sealed.toLocaleString()} of {t.total.toLocaleString()} rows sealed{t.unsealed ? ` · ${t.unsealed.toLocaleString()} older rows unsealed` : ''}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={!status.configured || !!busy} onClick={() => void verify(kind)} className={`${btn} bg-emerald-500 text-black hover:bg-emerald-400`}><ShieldCheck className="h-4 w-4" />{busy === `v-${kind}` ? 'Checking…' : 'Verify latest 5,000'}</button>
                {t.unsealed > 0 && <button type="button" disabled={!status.configured || !!busy} onClick={() => void sealOld(kind)} className={`${btn} border border-dark-border text-slate-200 hover:bg-dark-elevated`}><KeyRound className="h-4 w-4" />Seal older rows</button>}
              </div>
              {r && (
                <div className="mt-4 space-y-2 text-xs">
                  <p className="flex gap-4"><span className="text-emerald-400">✓ {r.ok} intact</span><span className={r.tampered ? 'font-bold text-rose-400' : 'text-slate-500'}>✗ {r.tampered} tampered</span><span className="text-slate-500">{r.unsealed} unsealed</span></p>
                  {r.tampered_rows.map((row) => (
                    <div key={row.id} className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3">
                      <p className="font-bold text-rose-200">{row.label} <span className="font-mono text-[10px] text-rose-300/70">{row.id}</span></p>
                      <p className="text-rose-200/80">{row.reason}</p>
                      {row.changes && Object.entries(row.changes).map(([f, c]) => <p key={f} className="font-mono text-[11px] text-rose-100">{f}: {JSON.stringify(c.sealed)} → {JSON.stringify(c.now)}</p>)}
                    </div>
                  ))}
                  {r.tampered === 0 && <p className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="h-4 w-4" />No edits outside the app were found.</p>}
                </div>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ Seed rotation
interface SeedEntry { seed: string; activated_at: string; by: string; retired_at?: string }
interface SeedState { active: SeedEntry | null; default_rule: string; history: SeedEntry[] }

const SeedTab: React.FC = () => {
  const [state, setState] = useState<SeedState | null>(null)
  const [custom, setCustom] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setState((await apiClient.get<SeedState>('/admin/fairness/client-seed')).data) } catch (e) { errorToast('Could not load seeds', e) }
  }, [])
  useEffect(() => { void load() }, [load])
  const rotate = async () => {
    if (!window.confirm('Rotate the public client seed? New rounds will use it; finished rounds are not affected.')) return
    setBusy(true)
    try {
      setState((await apiClient.post<SeedState>('/admin/fairness/client-seed/rotate', { seed: custom.trim() || null })).data)
      setCustom('')
      showToast({ title: 'Client seed rotated', message: 'New rounds now use the new seed.', type: 'success' })
    } catch (e) { errorToast('Rotation failed', e) } finally { setBusy(false) }
  }
  const valid = useMemo(() => !custom || /^[A-Za-z0-9_-]{8,64}$/.test(custom), [custom])
  if (!state) return <p className="text-xs text-slate-400">Loading…</p>
  return (
    <div className="space-y-6">
      <section className={card}>
        <h2 className="flex items-center gap-2 text-sm font-black text-white"><KeyRound className="h-4 w-4 text-amber-400" />Public client seed</h2>
        <p className="mt-1 max-w-2xl text-[11px] text-slate-500">Each outcome is HMAC-SHA256(server seed, "client seed:round number"). The server seed is new and secret for every round and is revealed when the round ends. The client seed is public; rotating it changes nothing that has already been drawn, and every old value stays listed so past rounds remain verifiable.</p>
        <div className="mt-4 rounded-xl bg-dark-elevated/50 p-4 text-xs">
          {state.active ? (
            <>
              <p className="text-slate-400">Active since {new Date(state.active.activated_at).toLocaleString()} · set by {state.active.by}</p>
              <p className="mt-1 break-all font-mono text-base text-white">{state.active.seed}</p>
            </>
          ) : <p className="text-slate-300">No platform seed set. {state.default_rule}</p>}
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="min-w-[240px] flex-1 text-xs text-slate-400">Custom seed (optional, 8–64 letters, numbers, - or _)
            <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Leave empty for a random 32-character seed" className={`${input} ${valid ? '' : 'border-rose-500'}`} />
          </label>
          <button type="button" disabled={busy || !valid} onClick={() => void rotate()} className={`${btn} bg-amber-400 text-black hover:bg-amber-300`}><RefreshCw className="h-4 w-4" />{busy ? 'Rotating…' : 'Rotate seed'}</button>
        </div>
      </section>
      <section className={card}>
        <h3 className="mb-2 text-sm font-black text-white">Previous seeds</h3>
        {state.history.length === 0 ? <p className="text-xs text-slate-400">No earlier seeds.</p> : (
          <table className="w-full text-xs">
            <thead><tr className="text-left text-slate-400"><th className="py-1.5">Seed</th><th className="py-1.5">Active from</th><th className="py-1.5">Until</th><th className="py-1.5">By</th></tr></thead>
            <tbody>{state.history.map((h) => (
              <tr key={h.seed + h.activated_at} className="border-t border-dark-border/50"><td className="py-1.5 font-mono text-slate-200">{h.seed}</td><td className="py-1.5 text-slate-400">{new Date(h.activated_at).toLocaleString()}</td><td className="py-1.5 text-slate-400">{h.retired_at ? new Date(h.retired_at).toLocaleString() : '—'}</td><td className="py-1.5 text-slate-400">{h.by}</td></tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </div>
  )
}

export const SecurityCenter: React.FC = () => {
  const [tab, setTab] = useState<Tab>('backtest')
  const tabs: [Tab, string][] = [['backtest', 'Backtest'], ['hold', 'Hold Analyzer'], ['integrity', 'Ledger Integrity'], ['seed', 'Seed Rotation']]
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Security & Fairness</h1>
        <p className="text-xs text-slate-400">Fair hold analysis, AES-256-GCM tamper evidence and provably-fair seed controls. Nothing on this page can choose or change a game result.</p>
      </div>
      <div className="flex gap-1 overflow-x-auto rounded-2xl border border-dark-border bg-dark-card p-1">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)} className={`whitespace-nowrap rounded-xl px-4 py-2 text-xs font-bold ${tab === id ? 'bg-emerald-500 text-black' : 'text-slate-300 hover:text-white'}`}>{label}</button>
        ))}
      </div>
      {tab === 'backtest' && <BacktestTab />}
      {tab === 'hold' && <HoldTab />}
      {tab === 'integrity' && <IntegrityTab />}
      {tab === 'seed' && <SeedTab />}
    </div>
  )
}
