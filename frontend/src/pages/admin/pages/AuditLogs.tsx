import React, { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { DataTable, type Column } from '../components/DataTable'
import { formatDateTime } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Input } from '../../../components/common/Input'

interface AuditItem {
  id: string
  actor_id: string
  actor_username: string | null
  action: string
  target_type: string
  target_id: string | null
  details: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

interface AuditResponse { items: AuditItem[]; total: number; total_pages: number }

const TARGET_TYPES = ['', 'USER', 'WALLET', 'GAME', 'ROUND', 'ROLE', 'SYSTEM', 'TICKET', 'NOTIFICATION']

export const AuditLogs: React.FC = () => {
  const [logs, setLogs] = useState<AuditItem[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [targetType, setTargetType] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(0)

  useEffect(() => { setPage(1) }, [q, targetType, from, to])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true)
      apiClient.get<AuditResponse>('/admin/audit-logs', {
        params: {
          page,
          page_size: 50,
          q: q.trim() || undefined,
          target_type: targetType || undefined,
          from_date: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
          to_date: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
        },
      })
        .then(({ data }) => { setLogs(data.items); setTotal(data.total); setPages(data.total_pages) })
        .catch(() => showToast({ title: 'Audit logs unavailable', message: 'Audit records could not be loaded.', type: 'error' }))
        .finally(() => setLoading(false))
    }, 300)
    return () => window.clearTimeout(timer)
  }, [q, targetType, from, to, page])

  const columns: Column<AuditItem>[] = [
    { header: 'Time', accessor: (item) => <span className="whitespace-nowrap text-slate-400">{formatDateTime(item.created_at)}</span> },
    { header: 'Admin', accessor: (item) => <span className="font-bold text-white">{item.actor_username || item.actor_id || 'system'}</span> },
    { header: 'Action', accessor: (item) => <span className="font-mono font-bold text-purple-300">{item.action}</span> },
    { header: 'Target', accessor: (item) => `${item.target_type}${item.target_id ? `: ${item.target_id.slice(0, 18)}` : ''}` },
    { header: 'Details', accessor: (item) => <span className="block max-w-xs truncate font-mono text-[11px]" title={JSON.stringify(item.details)}>{JSON.stringify(item.details)}</span> },
    { header: 'IP', accessor: (item) => <span className="font-mono text-slate-500">{item.ip_address || '—'}</span> },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-black text-white">Audit Logs</h1>
        <p className="text-xs text-slate-400">Who did what, when, to which record, and from which IP — {total} records</p>
      </div>
      <div className="grid gap-3 rounded-2xl border border-dark-border bg-dark-card p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Input label="Search" placeholder="admin, action, target id, IP…" value={q} onChange={(e) => setQ(e.target.value)} leftElement={<Search className="h-4 w-4 text-slate-400" />} />
        <label className="flex flex-col gap-1.5 text-xs font-semibold text-slate-300">Target type
          <select value={targetType} onChange={(e) => setTargetType(e.target.value)} className="rounded-xl border border-dark-border bg-dark-elevated px-3 py-2.5 text-sm text-white">
            {TARGET_TYPES.map((t) => <option key={t} value={t}>{t || 'All'}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-semibold text-slate-300">From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-sm text-white" />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-semibold text-slate-300">To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-sm text-white" />
        </label>
      </div>
      {loading && logs.length === 0 ? <p className="text-sm text-slate-400">Loading audit logs…</p> : logs.length
        ? <DataTable columns={columns} data={logs} keyExtractor={(item) => String(item.id)} />
        : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No audit records match these filters.</p>}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm text-slate-400">
          <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-dark-border p-1.5 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
          <span>Page {page} of {pages}</span>
          <button type="button" aria-label="Next page" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-dark-border p-1.5 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
        </div>
      )}
    </div>
  )
}
