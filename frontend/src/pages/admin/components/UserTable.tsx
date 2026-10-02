import React from 'react'
import { Link } from 'react-router-dom'
import { DataTable, type Column } from './DataTable'
import type { AdminUserRecord } from '../../../types/admin.types'
import { formatPaiseToRupee, formatDateTime } from '../../../utils/formatters'

export interface UserTableProps {
  users: AdminUserRecord[]
}

export const UserTable: React.FC<UserTableProps> = ({ users }) => {
  const columns: Column<AdminUserRecord>[] = [
    {
      header: 'User',
      accessor: (u) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-dark-elevated border border-dark-border flex items-center justify-center font-bold text-white">
            {u.username[0].toUpperCase()}
          </div>
          <div>
            <span className="font-bold text-white block">{u.username}</span>
            <span className="text-[10px] text-slate-500">{u.phone}</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Role',
      accessor: (u) => (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-purple-500/10 text-purple-400 border border-purple-500/30">
          {u.role}
        </span>
      ),
    },
    {
      header: 'Balance',
      align: 'right',
      accessor: (u) => (
        <span className="font-mono font-bold text-emerald-400">
          {formatPaiseToRupee(u.balancePaise)}
        </span>
      ),
    },
    {
      header: 'KYC',
      accessor: (u) => (
        <span
          className={`font-semibold ${
            u.kycStatus === 'verified'
              ? 'text-emerald-400'
              : u.kycStatus === 'pending'
              ? 'text-amber-400'
              : 'text-slate-500'
          }`}
        >
          {u.kycStatus ?? 'none'}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: (u) => (
        <span className={u.status === 'active' ? 'text-emerald-400' : 'text-rose-400 font-bold'}>
          {u.status}
        </span>
      ),
    },
    {
      header: 'Joined',
      accessor: (u) => <span className="text-slate-400">{formatDateTime(u.createdAt)}</span>,
    },
    {
      header: 'Action',
      align: 'right',
      accessor: (u) => (
        <Link
          to={`/admin/users/${u.id}`}
          className="text-xs font-bold text-purple-400 hover:text-purple-300"
        >
          Manage →
        </Link>
      ),
    },
  ]

  return <DataTable columns={columns} data={users} keyExtractor={(u) => u.id} />
}
