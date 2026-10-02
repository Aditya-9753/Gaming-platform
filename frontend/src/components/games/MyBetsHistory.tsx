import React, { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { apiClient } from '../../services/api'
import { formatPaiseToRupee } from '../../utils/formatters'
import { useAuthStore } from '../../store/auth.store'

export interface BetHistoryItem {
  entry_id: string
  game_id: string | null
  round_no: number | null
  bet_amount: number
  payout_amount: number
  multiplier: number | null
  status: string
  selection: Record<string, unknown> | null
  created_at: string
}

interface Page { items: BetHistoryItem[]; total_pages: number }

const GAME_LABEL: Record<string, string> = {
  aviator: 'Aviator',
  mines: 'Mines',
  color: 'Color',
  wingo_30s: 'WinGo 30s',
  wingo_1m: 'WinGo 1m',
  wingo_3m: 'WinGo 3m',
  wingo_5m: 'WinGo 5m',
}

/** Human readable pick for any game. */
export function describeSelection(item: BetHistoryItem): string {
  const s = item.selection ?? {}
  if (typeof s.type === 'string' && typeof s.value === 'string') {
    return s.type === 'NUMBER' ? `Number ${s.value}` : String(s.value).charAt(0) + String(s.value).slice(1).toLowerCase()
  }
  if (typeof s.mine_count === 'number') return `${s.mine_count} mines`
  if (typeof s.auto_cashout === 'number') return `Auto ${s.auto_cashout.toFixed(2)}x`
  if (typeof s.colour === 'string') return s.colour
  return item.game_id === 'aviator' ? 'Manual' : '—'
}

const statusClass: Record<string, string> = {
  WON: 'text-emerald-400',
  LOST: 'text-rose-400',
  PLACED: 'text-amber-400',
  IN_PROGRESS: 'text-amber-400',
  REFUNDED: 'text-slate-300',
}

export interface MyBetsHistoryProps {
  /** Filter to one game id; omit for every game. */
  gameId?: string
  pageSize?: number
  /** Bump to force a reload (e.g. after a round settles). */
  refreshKey?: number
  showGame?: boolean
  title?: string
}

export const MyBetsHistory: React.FC<MyBetsHistoryProps> = ({ gameId, pageSize = 10, refreshKey = 0, showGame = false, title }) => {
  const { isAuthenticated } = useAuthStore()
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page>({ items: [], total_pages: 0 })
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!isAuthenticated) return
    setLoading(true)
    try {
      const { data: body } = await apiClient.get<Page>('/history/bets', { params: { game_id: gameId, page, page_size: pageSize } })
      setData(body)
    } catch {
      /* transient */
    } finally {
      setLoading(false)
    }
  }, [gameId, page, pageSize, isAuthenticated])

  useEffect(() => { void load() }, [load, refreshKey])
  useEffect(() => { setPage(1) }, [gameId])

  if (!isAuthenticated) return <p className="p-4 text-center text-xs text-slate-400">Sign in to see your bet history.</p>

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        {title ? <h3 className="text-sm font-bold text-white">{title}</h3> : <span />}
        <button type="button" onClick={() => void load()} className="flex items-center gap-1 text-xs text-slate-400 hover:text-white"><RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />Refresh</button>
      </div>
      {data.items.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-400">{loading ? 'Loading…' : 'No bets yet.'}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-2 pr-2 font-semibold">Time</th>
                {showGame && <th className="py-2 pr-2 font-semibold">Game</th>}
                <th className="py-2 pr-2 font-semibold">Pick</th>
                <th className="py-2 pr-2 font-semibold text-right">Bet</th>
                <th className="py-2 pr-2 font-semibold text-right">Result</th>
                <th className="py-2 font-semibold text-right">Win</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.entry_id} className="border-t border-dark-border/60">
                  <td className="py-2 pr-2 text-slate-400 whitespace-nowrap">{new Date(item.created_at).toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' })}</td>
                  {showGame && <td className="py-2 pr-2 text-slate-300">{GAME_LABEL[item.game_id ?? ''] ?? item.game_id}</td>}
                  <td className="py-2 pr-2 text-slate-200">{describeSelection(item)}</td>
                  <td className="py-2 pr-2 text-right font-mono text-slate-200">{formatPaiseToRupee(item.bet_amount)}</td>
                  <td className={`py-2 pr-2 text-right font-bold ${statusClass[item.status] ?? 'text-slate-300'}`}>
                    {item.status === 'WON' && item.multiplier ? `${item.multiplier.toFixed(2)}x` : item.status === 'PLACED' ? 'Pending' : item.status}
                  </td>
                  <td className={`py-2 text-right font-mono ${item.payout_amount > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>{item.payout_amount > 0 ? formatPaiseToRupee(item.payout_amount) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-xs text-slate-400">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="p-1 rounded disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
          <span>{page} / {data.total_pages}</span>
          <button type="button" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)} className="p-1 rounded disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
        </div>
      )}
    </div>
  )
}
