import React, { useEffect, useState } from 'react'
import { DataTable, type Column } from '../components/DataTable'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'

interface Ticket {
  id: string
  user_id: string
  subject: string
  status: string
  created_at: string
}

interface TicketResponse { items: Ticket[] }

export const AdminSupport: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)

  const loadTickets = () => {
    apiClient.get<TicketResponse>('/admin/support/tickets', { params: { page: 1, page_size: 100 } })
      .then(({ data }) => setTickets(data.items))
      .catch(() => showToast({ title: 'Support queue unavailable', message: 'Could not load support tickets.', type: 'error' }))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadTickets() }, [])

  const handleResolve = async (ticket: Ticket) => {
    try {
      await apiClient.patch(`/admin/support/tickets/${ticket.id}/status`, { status: 'RESOLVED' })
      showToast({ title: 'Ticket updated', message: 'Ticket status was saved.', type: 'success' })
      loadTickets()
    } catch {
      showToast({ title: 'Update failed', message: 'Ticket status could not be changed.', type: 'error' })
    }
  }

  const columns: Column<Ticket>[] = [
    { header: 'Ticket ID', accessor: (ticket) => <span className="font-mono font-bold">#{ticket.id}</span> },
    { header: 'User', accessor: (ticket) => ticket.user_id },
    { header: 'Subject', accessor: 'subject' },
    { header: 'Status', accessor: (ticket) => <span className="capitalize">{ticket.status.toLowerCase()}</span> },
    {
      header: 'Action',
      align: 'right',
      accessor: (ticket) => !['resolved', 'closed'].includes(ticket.status.toLowerCase())
        ? <button onClick={() => void handleResolve(ticket)} className="text-xs font-bold text-emerald-400 hover:text-emerald-300">Mark resolved</button>
        : <span className="text-slate-500">Done</span>,
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Support Helpdesk Queue</h1>
        <p className="text-xs text-slate-400">Manage real user support tickets</p>
      </div>
      {loading ? <p className="text-sm text-slate-400">Loading tickets…</p> : tickets.length
        ? <DataTable columns={columns} data={tickets} keyExtractor={(ticket) => ticket.id} />
        : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No support tickets found.</p>}
    </div>
  )
}

export const Support = AdminSupport
