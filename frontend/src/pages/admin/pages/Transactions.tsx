import React, { useState } from 'react'
import { Download } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'

const dateInput = (date: Date) => date.toISOString().slice(0, 10)

export const Transactions: React.FC = () => {
  const [fromDate, setFromDate] = useState(() => dateInput(new Date(Date.now() - 30 * 86400000)))
  const [toDate, setToDate] = useState(() => dateInput(new Date()))
  const [loading, setLoading] = useState(false)

  const exportTransactions = async () => {
    if (fromDate > toDate) {
      showToast({ title: 'Invalid date range', message: 'Start date must not be after end date.', type: 'error' })
      return
    }
    setLoading(true)
    try {
      const { data } = await apiClient.get<Blob>('/admin/reports/export/transactions', {
        params: {
          from_date: `${fromDate}T00:00:00Z`,
          to_date: `${toDate}T23:59:59Z`,
        },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `transactions_${fromDate}_${toDate}.csv`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch {
      showToast({ title: 'Export failed', message: 'Transaction report could not be downloaded.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Transaction Reports</h1>
        <p className="text-xs text-slate-400">Export the server ledger for a selected date range.</p>
      </div>
      <section className="flex flex-col gap-4 rounded-2xl border border-dark-border bg-dark-card p-6 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-2 text-xs font-semibold text-slate-400">
          From
          <input type="date" value={fromDate} max={toDate} onChange={(event) => setFromDate(event.target.value)} className="rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 text-white" />
        </label>
        <label className="flex flex-1 flex-col gap-2 text-xs font-semibold text-slate-400">
          To
          <input type="date" value={toDate} min={fromDate} onChange={(event) => setToDate(event.target.value)} className="rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 text-white" />
        </label>
        <Button variant="primary" onClick={() => void exportTransactions()} disabled={loading} leftIcon={<Download className="h-4 w-4" />}>
          {loading ? 'Preparing…' : 'Download CSV'}
        </Button>
      </section>
      <p className="text-xs text-slate-500">The export is permission-protected and generated from persisted transaction records.</p>
    </div>
  )
}
