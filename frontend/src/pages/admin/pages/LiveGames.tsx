import React, { useCallback, useEffect, useState } from 'react'
import { Ban, Bomb, Pause, Play, Plane, Radio, ShieldCheck, Target } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Button } from '../../../components/common/Button'
import { Input } from '../../../components/common/Input'
import { Modal } from '../components/Modal'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'
import { useAuthStore } from '../../../store/auth.store'

interface AviatorRisk {
  status: string; round_id?: string; round_no?: number; multiplier?: number; bets?: number; total_bet?: number
  active_bets?: number; active_stake?: number; paid_out?: number; liability_now?: number
  top?: Array<{ username: string; amount: number; status: string; auto_cashout: number | null; payout: number }>
}
interface WingoRisk {
  game_id: string; status: string; round_id?: string; period?: string; bets?: number; total_bet?: number
  by_pick?: Record<string, { count: number; amount: number }>
  outcomes?: Array<{ number: number; bets: number; staked: number; payout: number; house_net: number }>
}
interface MinesRisk {
  active_sessions: number; total_stake: number; potential_payout: number
  sessions: Array<{ username: string; amount: number; mine_count: number; revealed: number; multiplier: number; potential_payout: number }>
}
interface RiskResponse { games: Record<string, boolean>; aviator: AviatorRisk; wingo: WingoRisk[]; mines: MinesRisk; generated_at: string }

const WINGO_LABEL: Record<string, string> = { wingo_30s: '30 sec', wingo_1m: '1 min', wingo_3m: '3 min', wingo_5m: '5 min' }
const pickName = (key: string) => {
  const [type, value] = key.split(':')
  return type === 'NUMBER' ? `Number ${value}` : value.charAt(0) + value.slice(1).toLowerCase()
}

const Stat: React.FC<{ label: string; value: React.ReactNode; tone?: string }> = ({ label, value, tone = 'text-white' }) => (
  <div className="rounded-xl bg-dark-elevated px-3 py-2">
    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
    <p className={`font-mono text-sm font-black ${tone}`}>{value}</p>
  </div>
)

export const LiveGames: React.FC = () => {
  const isSuper = useAuthStore((s) => s.user?.role === 'superadmin')
  const [data, setData] = useState<RiskResponse | null>(null)
  const [wingoTab, setWingoTab] = useState('wingo_30s')
  const [voidTarget, setVoidTarget] = useState<{ roundId: string; label: string } | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data: body } = await apiClient.get<RiskResponse>('/admin/risk/live')
      setData(body)
    } catch {
      /* keep last snapshot */
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = setInterval(() => void load(), 2000)
    return () => clearInterval(timer)
  }, [load])

  const toggleGame = async (gameId: string, active: boolean) => {
    try {
      await apiClient.patch(`/admin/games/${gameId}/status`, { is_active: active })
      showToast({ title: active ? 'Game resumed' : 'Game paused', message: active ? 'New rounds will start again.' : 'No new rounds or bets; the running round finishes normally.', type: 'success' })
      void load()
    } catch (error) {
      showToast({ title: 'Could not change status', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    }
  }

  const doVoid = async () => {
    if (!voidTarget) return
    setBusy(true)
    try {
      const { data: res } = await apiClient.post<{ refunded_entries: number; refunded_paise: number }>(`/admin/rounds/${voidTarget.roundId}/void`, { reason })
      showToast({ title: 'Round voided', message: `${res.refunded_entries} bets refunded (${formatPaiseToRupee(res.refunded_paise)}).`, type: 'success' })
      setVoidTarget(null); setReason('')
      void load()
    } catch (error) {
      showToast({ title: 'Could not void round', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const controls = (gameId: string, roundId?: string, label?: string) => {
    const active = data?.games[gameId] ?? true
    return (
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant={active ? 'secondary' : 'primary'} leftIcon={active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />} onClick={() => void toggleGame(gameId, !active)}>{active ? 'Pause' : 'Resume'}</Button>
        {isSuper && roundId && (
          <Button type="button" size="sm" variant="danger" leftIcon={<Ban className="h-3.5 w-3.5" />} onClick={() => setVoidTarget({ roundId, label: label ?? gameId })}>Void & refund</Button>
        )}
      </div>
    )
  }

  if (!data) return <p className="text-sm text-slate-400">Loading live exposure…</p>
  const av = data.aviator
  const wingo = data.wingo.find((w) => w.game_id === wingoTab) ?? data.wingo[0]
  const maxPayout = Math.max(1, ...(wingo?.outcomes ?? []).map((o) => o.payout))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-black text-white"><Radio className="h-6 w-6 text-rose-400" />Exposure Monitor</h1>
          <p className="text-xs text-slate-400">Read-only view of open stakes • refreshed every 2s • {new Date(data.generated_at).toLocaleTimeString()}</p>
        </div>
        <p className="flex max-w-md items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-200">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          Display only. Every result comes from the RNG (HMAC-SHA256 of a server seed committed before betting) and is never influenced by this screen — there is no way to see or set an outcome here. Controls: pause a game, or void a whole round (all stakes refunded, audit logged).
        </p>
      </div>

      {/* Aviator */}
      <section className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-black text-white"><Plane className="h-5 w-5 text-rose-400" />Aviator {av.round_no ? `· Round #${av.round_no}` : ''}
            <span className="rounded-full bg-dark-elevated px-2 py-0.5 text-[10px] font-bold text-slate-300">{av.status}</span>
            {!data.games.aviator && <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300">PAUSED</span>}
          </h2>
          {controls('aviator', av.round_id, `Aviator round #${av.round_no}`)}
        </div>
        {av.status === 'IDLE' ? <p className="text-sm text-slate-400">No round running.</p> : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="Multiplier" value={`${(av.multiplier ?? 1).toFixed(2)}x`} tone="text-violet-300" />
              <Stat label="Bets" value={av.bets ?? 0} />
              <Stat label="Total staked" value={formatPaiseToRupee(av.total_bet ?? 0)} />
              <Stat label="Still flying" value={formatPaiseToRupee(av.active_stake ?? 0)} tone="text-amber-300" />
              <Stat label="Liability now" value={formatPaiseToRupee(av.liability_now ?? 0)} tone="text-rose-300" />
              <Stat label="Cashed out" value={formatPaiseToRupee(av.paid_out ?? 0)} tone="text-emerald-300" />
            </div>
            {(av.top?.length ?? 0) > 0 && (
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-slate-400"><th className="py-1.5">Player</th><th className="py-1.5 text-right">Stake</th><th className="py-1.5 text-right">Auto</th><th className="py-1.5 text-right">Status</th><th className="py-1.5 text-right">Payout</th></tr></thead>
                  <tbody>
                    {av.top!.map((b, i) => (
                      <tr key={i} className="border-t border-dark-border/50">
                        <td className="py-1.5 text-white">{b.username}</td>
                        <td className="py-1.5 text-right font-mono">{formatPaiseToRupee(b.amount)}</td>
                        <td className="py-1.5 text-right font-mono text-slate-400">{b.auto_cashout ? `${b.auto_cashout.toFixed(2)}x` : '—'}</td>
                        <td className={`py-1.5 text-right font-bold ${b.status === 'WON' ? 'text-emerald-400' : b.status === 'LOST' ? 'text-rose-400' : 'text-amber-300'}`}>{b.status === 'PLACED' ? 'FLYING' : b.status}</td>
                        <td className="py-1.5 text-right font-mono text-emerald-400">{b.payout ? formatPaiseToRupee(b.payout) : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      {/* WinGo */}
      <section className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-black text-white"><Target className="h-5 w-5 text-emerald-400" />WinGo {wingo?.period ? `· ${wingo.period}` : ''}
            {wingo && <span className="rounded-full bg-dark-elevated px-2 py-0.5 text-[10px] font-bold text-slate-300">{wingo.status}</span>}
            {wingo && !data.games[wingo.game_id] && <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300">PAUSED</span>}
          </h2>
          {wingo && controls(wingo.game_id, wingo.round_id, `WinGo ${WINGO_LABEL[wingo.game_id]} ${wingo.period ?? ''}`)}
        </div>
        <div className="inline-flex rounded-full bg-dark-elevated p-0.5 text-xs font-bold">
          {data.wingo.map((w) => (
            <button key={w.game_id} type="button" onClick={() => setWingoTab(w.game_id)} className={`rounded-full px-3 py-1 ${w.game_id === wingoTab ? 'bg-emerald-500 text-dark-bg' : 'text-slate-400'}`}>
              {WINGO_LABEL[w.game_id]} <span className="opacity-70">({formatPaiseToRupee(w.total_bet ?? 0)})</span>
            </button>
          ))}
        </div>
        {!wingo || wingo.status === 'IDLE' ? <p className="text-sm text-slate-400">No period running.</p> : (
          <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
            <div>
              <p className="mb-2 text-xs font-bold text-slate-400">Stakes by pick · {wingo.bets} bets · {formatPaiseToRupee(wingo.total_bet ?? 0)}</p>
              <div className="space-y-1">
                {Object.entries(wingo.by_pick ?? {}).sort(([, a], [, b]) => b.amount - a.amount).map(([key, v]) => (
                  <div key={key} className="flex justify-between rounded-lg bg-dark-elevated px-3 py-1.5 text-xs">
                    <span className="text-white">{pickName(key)} <span className="text-slate-500">×{v.count}</span></span>
                    <span className="font-mono text-slate-200">{formatPaiseToRupee(v.amount)}</span>
                  </div>
                ))}
                {Object.keys(wingo.by_pick ?? {}).length === 0 && <p className="text-xs text-slate-500">No bets yet.</p>}
              </div>
            </div>
            <div className="overflow-x-auto">
              <p className="mb-2 text-xs font-bold text-slate-400">Per number — bets placed on it, and the house result if it is drawn (display calculation)</p>
              <table className="w-full min-w-[460px] text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-1.5">No.</th><th className="py-1.5 text-right">Bets</th><th className="py-1.5 text-right">Staked</th><th className="py-1.5 pl-3">Payout if drawn</th><th className="py-1.5 text-right">House P/L</th></tr></thead>
                <tbody>
                  {(wingo.outcomes ?? []).map((o) => (
                    <tr key={o.number} className="border-t border-dark-border/50">
                      <td className="py-1.5 font-black text-white">{o.number}</td>
                      <td className="py-1.5 text-right">{o.bets}</td>
                      <td className="py-1.5 text-right font-mono">{formatPaiseToRupee(o.staked)}</td>
                      <td className="py-1.5 pl-3">
                        <div className="flex items-center gap-2">
                          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-dark-elevated"><div className="h-full rounded-full bg-violet-500" style={{ width: `${(o.payout / maxPayout) * 100}%` }} /></div>
                          <span className="w-20 text-right font-mono text-slate-300">{formatPaiseToRupee(o.payout)}</span>
                        </div>
                      </td>
                      <td className={`py-1.5 text-right font-mono font-bold ${o.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{o.house_net >= 0 ? '+' : '−'}{formatPaiseToRupee(Math.abs(o.house_net))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* Mines */}
      <section className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-black text-white"><Bomb className="h-5 w-5 text-violet-400" />Mines
            {!data.games.mines && <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300">PAUSED</span>}
          </h2>
          {controls('mines')}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Active games" value={data.mines.active_sessions} />
          <Stat label="Total staked" value={formatPaiseToRupee(data.mines.total_stake)} />
          <Stat label="Potential payout" value={formatPaiseToRupee(data.mines.potential_payout)} tone="text-rose-300" />
        </div>
        {data.mines.sessions.length > 0 && (
          <table className="w-full text-xs">
            <thead><tr className="text-left text-slate-400"><th className="py-1.5">Player</th><th className="py-1.5 text-right">Stake</th><th className="py-1.5 text-right">Mines</th><th className="py-1.5 text-right">Gems</th><th className="py-1.5 text-right">Current</th><th className="py-1.5 text-right">If cashed</th></tr></thead>
            <tbody>
              {data.mines.sessions.map((s, i) => (
                <tr key={i} className="border-t border-dark-border/50">
                  <td className="py-1.5 text-white">{s.username}</td>
                  <td className="py-1.5 text-right font-mono">{formatPaiseToRupee(s.amount)}</td>
                  <td className="py-1.5 text-right">{s.mine_count}</td>
                  <td className="py-1.5 text-right">{s.revealed}</td>
                  <td className="py-1.5 text-right font-mono text-violet-300">{s.multiplier.toFixed(2)}x</td>
                  <td className="py-1.5 text-right font-mono text-amber-300">{formatPaiseToRupee(s.potential_payout)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <Modal open={voidTarget !== null} title="Void round & refund everyone" onClose={() => setVoidTarget(null)}>
        <p className="text-sm text-slate-300">Every open stake in <b className="text-white">{voidTarget?.label}</b> is refunded to the players. The drawn result itself is not changed. This is recorded in the audit log.</p>
        <div className="mt-4"><Input label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} minLength={3} placeholder="e.g. server incident" /></div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => setVoidTarget(null)}>Cancel</Button>
          <Button type="button" variant="danger" disabled={reason.trim().length < 3} isLoading={busy} onClick={() => void doVoid()}>Void & refund</Button>
        </div>
      </Modal>
    </div>
  )
}
