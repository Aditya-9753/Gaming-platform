import React from 'react'
import { DataTable, type Column } from './DataTable'
import type { WalletTransaction } from '../../../types/wallet.types'
import { formatPaiseToRupee, formatDateTime } from '../../../utils/formatters'

export interface TransactionTableProps {
  transactions: WalletTransaction[]
}

export const TransactionTable: React.FC<TransactionTableProps> = ({ transactions }) => {
  const columns: Column<WalletTransaction>[] = [
    {
      header: 'ID',
      accessor: (t) => <span className="font-mono text-slate-400">#{t.id.slice(-6)}</span>,
    },
    {
      header: 'User ID',
      accessor: (t) => <span className="font-mono text-slate-300">{t.userId}</span>,
    },
    {
      header: 'Type',
      accessor: (t) => (
        <span className="font-bold text-white capitalize">{t.type}</span>
      ),
    },
    {
      header: 'Amount',
      align: 'right',
      accessor: (t) => (
        <span
          className={`font-mono font-bold ${
            t.type === 'deposit' || t.type === 'win' || t.type === 'bonus'
              ? 'text-emerald-400'
              : 'text-rose-400'
          }`}
        >
          {t.type === 'deposit' || t.type === 'win' || t.type === 'bonus' ? '+' : '-'}
          {formatPaiseToRupee(t.amountPaise)}
        </span>
      ),
    },
    {
      header: 'Balance After',
      align: 'right',
      accessor: (t) => (
        <span className="font-mono text-slate-400">{formatPaiseToRupee(t.balanceAfterPaise)}</span>
      ),
    },
    {
      header: 'Status',
      accessor: (t) => (
        <span
          className={`font-semibold uppercase text-[10px] ${
            t.status === 'completed'
              ? 'text-emerald-400'
              : t.status === 'pending'
              ? 'text-amber-400'
              : 'text-rose-400'
          }`}
        >
          {t.status}
        </span>
      ),
    },
    {
      header: 'Timestamp',
      accessor: (t) => <span className="text-slate-400">{formatDateTime(t.createdAt)}</span>,
    },
  ]

  return <DataTable columns={columns} data={transactions} keyExtractor={(t) => t.id} />
}

