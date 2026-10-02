import React, { useEffect, useState } from 'react'
import { DataTable, type Column } from '../components/DataTable'
import { formatDateTime } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'

interface RoundRecord {
  round_id: string
  game_id: string
  round_no: number
  status: string
  server_seed_hash: string
  result: Record<string, unknown> | string | null
  started_at: string | null
  ended_at: string | null
}

interface RoundResponse { items: RoundRecord[] }

export const GameRounds: React.FC = () => {
  const [rounds, setRounds] = useState<RoundRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get<RoundResponse>('/admin/rounds', { params: { page: 1, page_size: 100 } })
      .then(({ data }) => setRounds(data.items))
      .catch(() => showToast({ title: 'Rounds unavailable', message: 'Historical rounds could not be loaded.', type: 'error' }))
      .finally(() => setLoading(false))
  }, [])

  const columns: Column<RoundRecord>[] = [
    { header: 'Game', accessor: 'game_id' },
    { header: 'Round', accessor: (round) => <span className="font-mono font-bold">#{round.round_no}</span> },
    { header: 'Status', accessor: (round) => <span className="capitalize">{round.status.toLowerCase()}</span> },
    { header: 'Result', accessor: (round) => <span className="font-mono text-emerald-400">{typeof round.result === 'string' ? round.result : round.result ? JSON.stringify(round.result) : '—'}</span> },
    { header: 'Server Hash', accessor: (round) => <span className="font-mono text-slate-500">{round.server_seed_hash}</span> },
    { header: 'Started', accessor: (round) => <span className="text-slate-400">{round.started_at ? formatDateTime(round.started_at) : '—'}</span> },
    { header: 'Ended', accessor: (round) => <span className="text-slate-400">{round.ended_at ? formatDateTime(round.ended_at) : '—'}</span> },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Game Rounds</h1>
        <p className="text-xs text-slate-400">Historical rounds and provably-fair server commitments</p>
      </div>
      {loading ? <p className="text-sm text-slate-400">Loading rounds…</p> : rounds.length
        ? <DataTable columns={columns} data={rounds} keyExtractor={(round) => round.round_id} />
        : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No rounds found.</p>}
    </div>
  )
}
