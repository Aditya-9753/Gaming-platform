import React, { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { DataTable, type Column } from '../components/DataTable'
import { Modal } from '../components/Modal'
import { Pagination } from '../../../components/common/Pagination'
import { formatDateTime, formatPaiseToRupee } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'

interface RoundRecord {
  round_id: string
  game_id: string
  round_no: number
  period?: string | null
  status: string
  outcome: string | null
  server_seed_hash: string
  server_seed: string | null
  bets: number
  wagered: number
  paid_out: number
  house_net: number
  started_at: string | null
  ended_at: string | null
  created_at: string | null
}

interface RoundResponse { items: RoundRecord[]; total: number; total_pages: number }

interface RoundDetails {
  round_id: string
  client_seed: string | null
  server_seed: string | null
  server_seed_hash: string
  entries: Array<{ entry_id: string; username: string | null; bet_amount: number; payout_amount: number; multiplier: number | null; status: string }>
}

const GAMES: Array<{ id: string; label: string }> = [
  { id: '', label: 'All games' },
  { id: 'aviator', label: 'Aviator' },
  { id: 'wingo_30s', label: 'WinGo 30s' },
  { id: 'wingo_1m', label: 'WinGo 1m' },
  { id: 'wingo_3m', label: 'WinGo 3m' },
  { id: 'wingo_5m', label: 'WinGo 5m' },
  { id: 'mines', label: 'Mines' },
]
const GAME_LABEL: Record<string, string> = Object.fromEntries(GAMES.filter((g) => g.id).map((g) => [g.id, g.label]))

const STATUSES = ['', 'COMPLETED', 'SETTLED', 'HISTORY', 'CRASHED', 'OPEN', 'BETTING_OPEN', 'RUNNING', 'LOCKED', 'CANCELLED']
const FINISHED = new Set(['COMPLETED', 'SETTLED', 'HISTORY', 'CRASHED'])
const PAGE_SIZE = 50
const REFRESH_MS = 5000

const statusTone = (status: string) =>
  FINISHED.has(status) ? 'bg-slate-700/60 text-slate-300'
    : status === 'CANCELLED' ? 'bg-rose-500/20 text-rose-300'
    : 'bg-emerald-500/20 text-emerald-300 animate-pulse'

export const GameRounds: React.FC = () => {
  const [rounds, setRounds] = useState<RoundRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [gameId, setGameId] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [total, setTotal] = useState(0)
  const [live, setLive] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [selected, setSelected] = useState<RoundRecord | null>(null)
  const [details, setDetails] = useState<RoundDetails | null>(null)

  const load = useCallback(async (quiet = false) => {
    try {
      const { data } = await apiClient.get<RoundResponse>('/admin/rounds', {
        params: { page, page_size: PAGE_SIZE, game_id: gameId || undefined, status: status || undefined },
      })
      setRounds(data.items)
      setTotal(data.total)
      setTotalPages(data.total_pages)
      setUpdatedAt(new Date())
    } catch {
      if (!quiet) showToast({ title: 'Rounds unavailable', message: 'Historical rounds could not be loaded.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [page, gameId, status])

  useEffect(() => { void load() }, [load])

  // Live refresh only on the first page (later pages would keep shifting)
  useEffect(() => {
    if (!live || page !== 1) return
    const timer = setInterval(() => { if (!document.hidden) void load(true) }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [live, page, load])

  useEffect(() => {
    if (!selected) { setDetails(null); return }
    apiClient.get<RoundDetails>(`/admin/rounds/${selected.round_id}`)
      .then(({ data }) => setDetails(data))
      .catch(() => showToast({ title: 'Round details unavailable', type: 'error' }))
  }, [selected])

  const columns: Column<RoundRecord>[] = [
    { header: 'Game', accessor: (r) => <span className="font-bold text-white">{GAME_LABEL[r.game_id] ?? r.game_id}</span> },
    { header: 'Round', accessor: (r) => <span className="font-mono font-bold">{r.period ?? `#${r.round_no}`}</span> },
    { header: 'Status', accessor: (r) => <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(r.status)}`}>{r.status.replace(/_/g, ' ').toLowerCase()}</span> },
    { header: 'Result', accessor: (r) => <span className="font-mono font-bold text-emerald-400">{r.outcome ?? (FINISHED.has(r.status) ? '—' : 'in play')}</span> },
    { header: 'Bets', accessor: (r) => r.bets, align: 'right' },
    { header: 'Wagered', accessor: (r) => <span className="font-mono">{formatPaiseToRupee(r.wagered)}</span>, align: 'right' },
    { header: 'Paid out', accessor: (r) => <span className="font-mono">{formatPaiseToRupee(r.paid_out)}</span>, align: 'right' },
    { header: 'House', accessor: (r) => <span className={`font-mono font-bold ${r.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{formatPaiseToRupee(r.house_net)}</span>, align: 'right' },
    { header: 'Time', accessor: (r) => { const t = r.ended_at ?? r.started_at ?? r.created_at; return <span className="text-slate-400">{t ? formatDateTime(t) : '—'}</span> } },
    { header: '', accessor: (r) => <button type="button" onClick={() => setSelected(r)} className="text-xs font-bold text-purple-300 hover:underline">Details</button> },
  ]

  const selectClass = 'rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-xs font-bold text-white'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Game Rounds</h1>
          <p className="text-xs text-slate-400">
            Newest first • real-player money only (lobby bots excluded) • {total.toLocaleString('en-IN')} rounds
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Game" value={gameId} onChange={(e) => { setGameId(e.target.value); setPage(1) }} className={selectClass}>
            {GAMES.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
          </select>
          <select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className={selectClass}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, ' ').toLowerCase() : 'Any status'}</option>)}
          </select>
          <button type="button" onClick={() => setLive((v) => !v)} className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-bold ${live ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-dark-border bg-dark-elevated text-slate-400'}`}>
            <RefreshCw className={`h-3.5 w-3.5 ${live && page === 1 ? 'animate-spin [animation-duration:3s]' : ''}`} />
            {live ? 'Live' : 'Paused'}
          </button>
        </div>
      </div>
      {updatedAt && <p className="text-[11px] text-slate-500">Updated {updatedAt.toLocaleTimeString()}{live && page !== 1 ? ' • live refresh runs on page 1' : ''}</p>}

      {loading ? <p className="text-sm text-slate-400">Loading rounds…</p> : rounds.length
        ? <DataTable columns={columns} data={rounds} keyExtractor={(r) => r.round_id} />
        : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No rounds match these filters.</p>}
      <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />

      <Modal open={selected !== null} title={selected ? `${GAME_LABEL[selected.game_id] ?? selected.game_id} • ${selected.period ?? `#${selected.round_no}`}` : ''} onClose={() => setSelected(null)} wide>
        {selected && (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ['Result', selected.outcome ?? '—'],
                ['Bets', String(selected.bets)],
                ['Wagered', formatPaiseToRupee(selected.wagered)],
                ['House', formatPaiseToRupee(selected.house_net)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-dark-elevated p-3"><p className="text-slate-500">{k}</p><p className="font-mono font-black text-white">{v}</p></div>
              ))}
            </div>
            <div className="space-y-1 break-all rounded-xl bg-dark-elevated p-3 font-mono text-slate-400">
              <p>Seed hash: {selected.server_seed_hash}</p>
              <p>Server seed: {details?.server_seed ?? 'hidden until the round finishes'}</p>
              {details?.client_seed && <p>Client seed: {details.client_seed}</p>}
            </div>
            {!details ? <p className="text-slate-400">Loading bets…</p> : details.entries.length === 0 ? <p className="text-slate-400">No bets in this round.</p> : (
              <div className="max-h-72 overflow-auto">
                <table className="w-full">
                  <thead><tr className="text-left text-slate-500"><th className="py-1">Player</th><th className="py-1 text-right">Bet</th><th className="py-1 text-right">X</th><th className="py-1 text-right">Payout</th><th className="py-1 text-right">Status</th></tr></thead>
                  <tbody>
                    {details.entries.map((e) => (
                      <tr key={e.entry_id} className="border-t border-dark-border">
                        <td className="py-1 text-slate-200">{e.username ?? '—'}</td>
                        <td className="py-1 text-right font-mono">{formatPaiseToRupee(e.bet_amount)}</td>
                        <td className="py-1 text-right font-mono">{e.multiplier ? `${e.multiplier.toFixed(2)}x` : ''}</td>
                        <td className="py-1 text-right font-mono text-emerald-400">{e.payout_amount ? formatPaiseToRupee(e.payout_amount) : ''}</td>
                        <td className="py-1 text-right capitalize text-slate-400">{e.status.toLowerCase()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
