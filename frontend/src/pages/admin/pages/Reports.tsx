import React, { useEffect, useState } from 'react'
import { AreaChart } from '../components/Charts'
import { StatCard } from '../components/StatCard'
import { ArrowDownLeft, IndianRupee, TrendingUp } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { showToast } from '../../../components/common/Toast'

interface DashboardStats {
  chart_series: Array<{ date: string; wagered: number; payout: number; new_users: number }>
}

export const Reports: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    apiClient.get<DashboardStats>('/admin/dashboard/stats')
      .then(({ data }) => setStats(data))
      .catch(() => {
        setFailed(true)
        showToast({ title: 'Reports unavailable', message: 'Report metrics could not be loaded.', type: 'error' })
      })
  }, [])

  const series = stats?.chart_series ?? []
  const totalWagered = series.reduce((total, day) => total + day.wagered, 0)
  const totalPayout = series.reduce((total, day) => total + day.payout, 0)
  const ggr = totalWagered - totalPayout
  const chartData = series.map((day) => ({
    label: new Date(day.date).toLocaleDateString(undefined, { weekday: 'short' }),
    value: day.wagered / 100,
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Platform Reports</h1>
        <p className="text-xs text-slate-400">Persisted wager and payout totals for the last seven days.</p>
      </div>
      {!stats ? <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">{failed ? 'Report metrics could not be loaded.' : 'Loading report metrics…'}</p> : <>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="7-Day Wagered" value={formatPaiseToRupee(totalWagered)} icon={<IndianRupee className="h-5 w-5 text-emerald-400" />} />
          <StatCard label="7-Day Payouts" value={formatPaiseToRupee(totalPayout)} icon={<ArrowDownLeft className="h-5 w-5 text-purple-400" />} />
          <StatCard label="7-Day Net" value={formatPaiseToRupee(ggr)} icon={<TrendingUp className="h-5 w-5 text-amber-400" />} />
        </div>
        <div className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-6 shadow-xl">
          <h3 className="text-base font-bold text-white">Daily wagered volume</h3>
          {chartData.length ? <AreaChart data={chartData} height={220} color="#a855f7" /> : <p className="text-sm text-slate-400">No report data is available.</p>}
        </div>
      </>}
    </div>
  )
}
