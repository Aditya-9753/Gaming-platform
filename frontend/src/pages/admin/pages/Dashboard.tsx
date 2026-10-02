import React, { useEffect, useState } from 'react'
import { Users, IndianRupee, Trophy, Gamepad2 } from 'lucide-react'
import { StatCard } from '../components/StatCard'
import { AreaChart } from '../components/Charts'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { showToast } from '../../../components/common/Toast'

interface DashboardStats {
  users: number
  active_users: number
  live_games: number
  active_ws_sessions: number
  rounds_played: number
  credit_in: number
  credit_out: number
  open_tickets: number
  chart_series: Array<{ date: string; wagered: number; payout: number; new_users: number }>
}

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    apiClient.get<DashboardStats>('/admin/dashboard/stats')
      .then(({ data }) => setStats(data))
      .catch(() => {
        setFailed(true)
        showToast({ title: 'Dashboard unavailable', message: 'Metrics could not be loaded. Check your admin permission and server connection.', type: 'error' })
      })
  }, [])

  const chart = (stats?.chart_series || []).map((item) => ({
    label: new Date(item.date).toLocaleDateString(undefined, { weekday: 'short' }),
    value: item.wagered / 100,
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Platform Operations Center</h1>
        <p className="text-xs text-slate-400">Live metrics from the administrative API</p>
      </div>
      {!stats ? <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">{failed ? 'Metrics could not be loaded.' : 'Loading platform metrics…'}</p> : <>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total Users" value={stats.users.toLocaleString()} icon={<Users className="h-5 w-5 text-emerald-400" />} />
          <StatCard label="Promotional Credits" value={formatPaiseToRupee(stats.credit_in)} icon={<IndianRupee className="h-5 w-5 text-purple-400" />} />
          <StatCard label="Total Wagered" value={formatPaiseToRupee(stats.credit_out)} icon={<Trophy className="h-5 w-5 text-amber-400" />} />
          <StatCard label="Rounds Played" value={stats.rounds_played.toLocaleString()} icon={<Gamepad2 className="h-5 w-5 text-cyan-400" />} />
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs text-slate-400 sm:grid-cols-3">
          <p className="rounded-xl border border-dark-border bg-dark-card p-3">Active users (24h): <strong className="text-white">{stats.active_users.toLocaleString()}</strong></p>
          <p className="rounded-xl border border-dark-border bg-dark-card p-3">Enabled games: <strong className="text-white">{stats.live_games}</strong></p>
          <p className="rounded-xl border border-dark-border bg-dark-card p-3">Active WebSocket sessions: <strong className="text-white">{stats.active_ws_sessions}</strong></p>
          <p className="rounded-xl border border-dark-border bg-dark-card p-3">Open support tickets: <strong className="text-white">{stats.open_tickets}</strong></p>
        </div>
        <div className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-6 shadow-xl">
          <div><h3 className="text-base font-bold text-white">Daily wagered credits</h3><p className="text-xs text-slate-400">Last seven days</p></div>
          {chart.length > 0 ? <AreaChart data={chart} height={200} color="#10b981" /> : <p className="text-sm text-slate-400">No chart data is available.</p>}
        </div>
      </>}
    </div>
  )
}
