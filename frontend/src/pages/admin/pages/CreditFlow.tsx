import React, { useEffect, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Coins, Landmark, Wallet } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'

interface Overview {
  window_days: number
  wallets: { count: number; total_balance: number; locked: number }
  transactions: Record<string, { count: number; amount: number }>
  games: Array<{ game_id: string; bets: number; wagered: number; paid_out: number; house_net: number }>
  totals: { wagered: number; paid_out: number; house_net: number }
  demo_credits: { count: number; amount: number }
}

const WINDOWS: Array<[number, string]> = [[1, 'Today (24h)'], [7, '7 days'], [30, '30 days'], [3650, 'All time']]
const GAME_LABEL: Record<string, string> = {
  teen_patti: 'Teen Patti',
  aviator: 'Aviator', mines: 'Mines', color: 'Color (legacy)', wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m',
}
const TX_LABEL: Record<string, string> = {
  BET: 'Bets placed', WIN: 'Winnings paid', REFUND: 'Refunds', FAUCET: 'Sign-up / faucet', BONUS: 'Bonuses & demo credits', ADJUSTMENT: 'Manual adjustments',
}

const Card: React.FC<{ label: string; value: string; icon: React.ReactNode; tone?: string; sub?: string }> = ({ label, value, icon, tone = 'text-white', sub }) => (
  <div className="rounded-2xl border border-dark-border bg-dark-card p-4">
    <p className="flex items-center gap-2 text-xs font-bold text-slate-400">{icon}{label}</p>
    <p className={`mt-2 font-mono text-xl font-black ${tone}`}>{value}</p>
    {sub && <p className="mt-1 text-[11px] text-slate-500">{sub}</p>}
  </div>
)

/** Super-admin view of the whole virtual-credit economy. */
export const CreditFlow: React.FC = () => {
  const [days, setDays] = useState(1)
  const [data, setData] = useState<Overview | null>(null)

  useEffect(() => {
    apiClient.get<Overview>('/admin/finance/overview', { params: { days } })
      .then(({ data: body }) => setData(body))
      .catch((error) => showToast({ title: 'Credit flow unavailable', message: getApiErrorMessage(error, 'Super admin only.'), type: 'error' }))
  }, [days])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Credit Flow</h1>
          <p className="text-xs text-slate-400">Where virtual credits came from and went — visible to the super admin only.</p>
        </div>
        <div className="inline-flex rounded-full border border-dark-border bg-dark-card p-0.5 text-xs font-bold">
          {WINDOWS.map(([d, label]) => (
            <button key={d} type="button" onClick={() => setDays(d)} className={`rounded-full px-3 py-1.5 ${days === d ? 'bg-emerald-500 text-dark-bg' : 'text-slate-400'}`}>{label}</button>
          ))}
        </div>
      </div>

      {!data ? <p className="text-sm text-slate-400">Loading…</p> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card label="Total wagered" value={formatPaiseToRupee(data.totals.wagered)} icon={<ArrowDownRight className="h-4 w-4 text-sky-400" />} />
            <Card label="Paid to players" value={formatPaiseToRupee(data.totals.paid_out)} icon={<ArrowUpRight className="h-4 w-4 text-amber-400" />} />
            <Card label="House result" value={`${data.totals.house_net >= 0 ? '+' : '−'}${formatPaiseToRupee(Math.abs(data.totals.house_net))}`} tone={data.totals.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'} icon={<Landmark className="h-4 w-4 text-emerald-400" />}
              sub={data.totals.wagered ? `Hold ${((data.totals.house_net / data.totals.wagered) * 100).toFixed(2)}%` : undefined} />
            <Card label="Credits in wallets" value={formatPaiseToRupee(data.wallets.total_balance)} icon={<Wallet className="h-4 w-4 text-purple-400" />} sub={`${data.wallets.count} wallets · ${formatPaiseToRupee(data.wallets.locked)} in open bets`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
              <h2 className="mb-3 text-sm font-black text-white">By game</h2>
              <table className="w-full text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-1.5">Game</th><th className="py-1.5 text-right">Bets</th><th className="py-1.5 text-right">Wagered</th><th className="py-1.5 text-right">Paid</th><th className="py-1.5 text-right">House</th></tr></thead>
                <tbody>
                  {data.games.map((g) => (
                    <tr key={g.game_id} className="border-t border-dark-border/50">
                      <td className="py-2 font-bold text-white">{GAME_LABEL[g.game_id] ?? g.game_id}</td>
                      <td className="py-2 text-right">{g.bets.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.wagered)}</td>
                      <td className="py-2 text-right font-mono">{formatPaiseToRupee(g.paid_out)}</td>
                      <td className={`py-2 text-right font-mono font-bold ${g.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{g.house_net >= 0 ? '+' : '−'}{formatPaiseToRupee(Math.abs(g.house_net))}</td>
                    </tr>
                  ))}
                  {data.games.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-slate-500">No settled bets in this window.</td></tr>}
                </tbody>
              </table>
            </section>

            <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
              <h2 className="mb-3 text-sm font-black text-white">Ledger movements</h2>
              <div className="space-y-1.5">
                {Object.entries(data.transactions).sort(([, a], [, b]) => b.amount - a.amount).map(([type, v]) => (
                  <div key={type} className="flex justify-between rounded-lg bg-dark-elevated px-3 py-2 text-xs">
                    <span className="text-white">{TX_LABEL[type] ?? type} <span className="text-slate-500">· {v.count.toLocaleString()} tx</span></span>
                    <span className="font-mono text-slate-200">{formatPaiseToRupee(v.amount)}</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                <Coins className="h-4 w-4" />Demo credits given to staff: {formatPaiseToRupee(data.demo_credits.amount)} ({data.demo_credits.count} grants)
              </p>
            </section>
          </div>
          <p className="text-[11px] text-slate-500">All figures are virtual credits (₹ shown for readability) — no real money moves on this platform.</p>
        </>
      )}
    </div>
  )
}
