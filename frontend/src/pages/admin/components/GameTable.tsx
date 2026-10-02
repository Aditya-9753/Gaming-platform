import React from 'react'
import { Link } from 'react-router-dom'
import { DataTable, type Column } from './DataTable'
import type { GameMetadata } from '../../../types/game.types'
import { formatPaiseToRupee } from '../../../utils/formatters'

export interface GameTableProps {
  games: GameMetadata[]
  onToggleStatus?: (id: string, active: boolean) => void
}

export const GameTable: React.FC<GameTableProps> = ({ games }) => {
  const columns: Column<GameMetadata>[] = [
    {
      header: 'Game',
      accessor: (g) => (
        <div>
          <span className="font-bold text-white block">{g.name}</span>
          <span className="text-[10px] text-slate-500 capitalize">{g.id}</span>
        </div>
      ),
    },
    {
      header: 'RTP',
      accessor: (g) => <span className="font-mono text-slate-200">{g.rtpPercent}%</span>,
    },
    {
      header: 'House Edge',
      accessor: (g) => <span className="font-mono text-purple-400">{g.houseEdgePercent}%</span>,
    },
    {
      header: 'Min Bet',
      accessor: (g) => (
        <span className="font-mono text-slate-300">{formatPaiseToRupee(g.minBetPaise)}</span>
      ),
    },
    {
      header: 'Max Bet',
      accessor: (g) => (
        <span className="font-mono text-slate-300">{formatPaiseToRupee(g.maxBetPaise)}</span>
      ),
    },
    {
      header: 'Live Players',
      accessor: (g) => <span className="font-bold text-white">{g.currentPlayersCount}</span>,
    },
    {
      header: 'Status',
      accessor: (g) => (
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase ${
            g.isActive
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
          }`}
        >
          {g.isActive ? 'Active' : 'Maintenance'}
        </span>
      ),
    },
    {
      header: 'Configure',
      align: 'right',
      accessor: (g) => (
        <Link
          to={`/admin/game-settings?id=${g.id}`}
          className="text-xs font-bold text-purple-400 hover:text-purple-300"
        >
          Edit Limits
        </Link>
      ),
    },
  ]

  return <DataTable columns={columns} data={games} keyExtractor={(g) => g.id} />
}
