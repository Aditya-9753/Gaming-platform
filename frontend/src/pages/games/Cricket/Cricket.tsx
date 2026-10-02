import React, { useCallback, useEffect, useState } from 'react'
import { Activity, RefreshCw, Trophy, Clock, MapPin, Info } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'
import { apiClient } from '../../../services/api'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'
import { WS_BASE_URL } from '../../../utils/constants'
import { syncWalletBalance } from '../../../services/wallet.api'

interface CricketMatch {
  match_id: string
  home_team: string
  away_team: string
  status: string
  home_score?: string | null
  away_score?: string | null
  winner?: string | null
  abandoned?: boolean
  odds?: { HOME?: number; AWAY?: number }
  metadata?: {
    competition?: string
    category?: string
    venue?: string
    starts_at?: number | null
    logos?: Record<string, string | null>
    format?: string
    betting_closes_at?: number
    batting?: string
    target?: number | null
    this_over?: string[]
    result?: string
  }
}

interface MyPrediction {
  prediction_id: string
  match_id: string
  team: string
  home_team: string
  away_team: string
  stake: number
  odds: number
  payout: number
  status: 'PLACED' | 'WON' | 'LOST' | 'REFUNDED' | string
  match_status: string
}

const OPEN_STATUSES = ['SCHEDULED', 'UPCOMING', 'NOT_STARTED']
type StatusFilter = 'ALL' | 'LIVE' | 'UPCOMING' | 'RESULTS'
const STATUS_FILTERS: Array<[StatusFilter, string]> = [['ALL', 'All'], ['LIVE', 'Live'], ['UPCOMING', 'Upcoming'], ['RESULTS', 'Results']]
const STATUS_ORDER: Record<string, number> = { LIVE: 0, SCHEDULED: 1, COMPLETED: 2, ABANDONED: 3 }

const statusMatches = (status: string, filter: StatusFilter) =>
  filter === 'ALL' || (filter === 'LIVE' && status === 'LIVE') || (filter === 'UPCOMING' && OPEN_STATUSES.includes(status)) || (filter === 'RESULTS' && (status === 'COMPLETED' || status === 'ABANDONED'))

const TeamLogo: React.FC<{ name: string; src?: string | null }> = ({ name, src }) => (
  src
    ? <img src={src} alt="" loading="lazy" className="h-8 w-8 rounded-full bg-white object-contain p-0.5" />
    : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500/20 text-[10px] font-black text-blue-300">{name.split(/\s+/).map((w) => w[0]).join('').slice(0, 3).toUpperCase()}</span>
)

const ballClass = (ball: string) =>
  ball === 'W'
    ? 'bg-rose-500 text-white'
    : ball === '4' || ball === '6'
      ? 'bg-emerald-500 text-dark-bg'
      : 'bg-dark-elevated text-slate-300 border border-dark-border'

const statusPill: Record<string, string> = {
  LIVE: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
  SCHEDULED: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  COMPLETED: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
}

const predictionPill: Record<string, string> = {
  PLACED: 'text-amber-400',
  WON: 'text-emerald-400',
  LOST: 'text-rose-400',
  REFUNDED: 'text-slate-300',
}

export const Cricket: React.FC = () => {
  const [matches, setMatches] = useState<CricketMatch[]>([])
  const [source, setSource] = useState<'cricapi' | 'simulated' | ''>('')
  const [category, setCategory] = useState('All')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [mine, setMine] = useState<MyPrediction[]>([])
  const [stake, setStake] = useState('10')
  const [loading, setLoading] = useState(true)
  const [placing, setPlacing] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [key, rotateKey] = useIdempotencyKey()

  const refreshMine = useCallback(async () => {
    try {
      const { data } = await apiClient.get<{ items: MyPrediction[] }>('/games/cricket/predictions/me')
      setMine((previous) => {
        // Celebrate predictions that just settled.
        for (const item of data.items) {
          const before = previous.find((p) => p.prediction_id === item.prediction_id)
          if (before?.status === 'PLACED' && item.status !== 'PLACED') {
            if (item.status === 'WON') showToast({ title: 'Prediction won!', message: `${item.team} won — you get ${formatPaiseToRupee(item.payout)}.`, type: 'success' })
            else if (item.status === 'LOST') showToast({ title: 'Prediction lost', message: `${item.team} did not win. Stake ${formatPaiseToRupee(item.stake)} lost.`, type: 'error' })
            void syncWalletBalance().catch(() => undefined)
          }
        }
        return data.items
      })
    } catch {
      /* not signed in or transient — ignore */
    }
  }, [])

  const refreshMatches = useCallback(async () => {
    try {
      const { data } = await apiClient.get<{ items: CricketMatch[]; source?: 'cricapi' | 'simulated' }>('/games/cricket/matches')
      setMatches(data.items)
      setSource(data.source ?? '')
    } catch {
      showToast({ title: 'Cricket feed unavailable', message: 'Could not load matches from the server.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshMatches()
    void refreshMine()
    const refresh = setInterval(() => { void refreshMatches(); void refreshMine() }, 10000)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    let disposed = false
    let reconnect: ReturnType<typeof setTimeout>
    let throttle: ReturnType<typeof setTimeout> | null = null
    let socket: WebSocket | null = null
    const connect = () => {
      if (disposed) return
      socket = new WebSocket(`${WS_BASE_URL.replace(/\/$/, '')}/games/cricket`)
      socket.onmessage = (message) => {
        let type = ''
        try { type = (JSON.parse(message.data) as { type?: string }).type ?? '' } catch { return }
        if (type === 'market_settled') void refreshMine()
        if (throttle) return
        throttle = setTimeout(() => { throttle = null; void refreshMatches() }, 800)
      }
      socket.onclose = () => { if (!disposed) reconnect = setTimeout(connect, 2000) }
      socket.onerror = () => socket?.close()
    }
    connect()
    return () => {
      disposed = true
      clearInterval(refresh)
      clearInterval(tick)
      clearTimeout(reconnect)
      if (throttle) clearTimeout(throttle)
      socket?.close()
    }
  }, [refreshMatches, refreshMine])

  const categories = ['All', ...Array.from(new Set(matches.map((m) => m.metadata?.category ?? 'Other')))]
  const visible = matches
    .filter((m) => category === 'All' || (m.metadata?.category ?? 'Other') === category)
    .filter((m) => statusMatches(m.status.toUpperCase(), statusFilter))
    .sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) || (a.metadata?.starts_at ?? 0) - (b.metadata?.starts_at ?? 0))

  const handleBet = async (match: CricketMatch, selection: 'HOME' | 'AWAY') => {
    const value = Number(stake)
    if (!Number.isFinite(value) || value <= 0 || placing) return
    setPlacing(match.match_id)
    try {
      await apiClient.post('/games/cricket/predictions', {
        match_id: match.match_id,
        selection,
        stake: rupeeToPaise(value),
      }, { headers: { 'Idempotency-Key': key } })
      rotateKey()
      void syncWalletBalance().catch(() => undefined)
      void refreshMine()
      const team = selection === 'HOME' ? match.home_team : match.away_team
      showToast({ title: 'Prediction placed', message: `₹${value} on ${team} to win.`, type: 'success' })
    } catch (error) {
      rotateKey()
      showToast({ title: 'Prediction rejected', message: getApiErrorMessage(error, 'The market may be closed or your stake is outside limits.'), type: 'error' })
    } finally {
      setPlacing(null)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between gap-3 bg-dark-card border border-dark-border p-4 rounded-2xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400"><Activity className="w-6 h-6" /></div>
          <div>
            <h2 className="text-lg font-black text-white">Cricket Match Winner</h2>
            <span className="text-xs text-slate-400">Pick the winner before the toss • live ball-by-ball</span>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => { void refreshMatches(); void refreshMine() }} leftIcon={<RefreshCw className="w-4 h-4" />}>Refresh</Button>
      </div>

      <label className="block text-xs text-slate-400">Prediction stake (₹)
        <input type="number" min="1" step="1" value={stake} onChange={(event) => setStake(event.target.value)} className="mt-2 w-full max-w-xs bg-dark-elevated border border-dark-border rounded-xl px-3 py-2 text-sm font-mono font-bold text-white" />
      </label>

      {source === 'simulated' && (
        <p className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          Showing the Virtual League. Add a free CRICAPI_KEY from cricketdata.org to backend/.env to show every real match being played worldwide.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {categories.map((c) => (
          <button key={c} type="button" onClick={() => setCategory(c)} className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${category === c ? 'bg-blue-500 text-white' : 'bg-dark-card border border-dark-border text-slate-400 hover:text-white'}`}>
            {c} <span className="opacity-70">({c === 'All' ? matches.length : matches.filter((m) => (m.metadata?.category ?? 'Other') === c).length})</span>
          </button>
        ))}
      </div>
      <div className="inline-flex rounded-full bg-dark-card border border-dark-border p-0.5 text-xs font-bold">
        {STATUS_FILTERS.map(([key, label]) => (
          <button key={key} type="button" onClick={() => setStatusFilter(key)} className={`rounded-full px-4 py-1 ${statusFilter === key ? 'bg-dark-elevated text-white' : 'text-slate-400'}`}>{label}</button>
        ))}
      </div>

      {loading ? <p className="text-sm text-slate-400">Loading matches…</p> : visible.length === 0 ? (
        <div className="rounded-2xl border border-dark-border bg-dark-card p-6 text-center text-sm text-slate-400">No matches in this view right now.</div>
      ) : visible.map((match) => {
        const status = match.status.toUpperCase()
        const open = OPEN_STATUSES.includes(status)
        const meta = match.metadata ?? {}
        const closesIn = meta.betting_closes_at ? Math.max(0, Math.round(meta.betting_closes_at - now / 1000)) : null
        const myPick = mine.find((p) => p.match_id === match.match_id)
        return (
          <article key={match.match_id} className="rounded-2xl border border-dark-border bg-dark-card p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="flex flex-wrap items-center gap-1.5 text-slate-400">
                {meta.category && <span className="rounded bg-blue-500/15 px-1.5 py-0.5 font-bold text-blue-300">{meta.category}</span>}
                {meta.format && <span className="rounded bg-dark-elevated px-1.5 py-0.5 font-bold text-slate-300">{meta.format}</span>}
                <span>{meta.competition ?? 'Cricket'}</span>
              </span>
              <span className={`px-2 py-0.5 rounded-full border font-bold ${statusPill[status] ?? statusPill.COMPLETED}`}>
                {status === 'LIVE' ? '● LIVE' : status === 'SCHEDULED' ? 'BETTING OPEN' : status}
              </span>
            </div>

            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
              <div className="flex items-center gap-2">
                <TeamLogo name={match.home_team} src={meta.logos?.[match.home_team]} />
                <div>
                <p className="font-black text-white">{match.home_team}</p>
                <p className="font-mono text-sm text-emerald-400">{match.home_score ?? '—'}</p>
                </div>
              </div>
              <span className="text-xs text-slate-500">vs</span>
              <div className="flex items-center justify-end gap-2 text-right">
                <div>
                  <p className="font-black text-white">{match.away_team}</p>
                  <p className="font-mono text-sm text-emerald-400">{match.away_score ?? '—'}</p>
                </div>
                <TeamLogo name={match.away_team} src={meta.logos?.[match.away_team]} />
              </div>
            </div>

            {status === 'LIVE' && (
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-dark-border text-xs">
                <span className="text-slate-400">
                  {meta.batting ? `${meta.batting} batting` : ''}{meta.target ? ` • target ${meta.target}` : ''}
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="text-slate-400 font-semibold">This over:</span>
                  {(meta.this_over ?? []).map((ball, index) => (
                    <span key={index} className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-black font-mono ${ballClass(ball)}`}>{ball}</span>
                  ))}
                </div>
              </div>
            )}

            {meta.venue && <p className="flex items-center gap-1 text-[11px] text-slate-500"><MapPin className="h-3 w-3" />{meta.venue}{meta.starts_at ? ` • ${new Date(meta.starts_at * 1000).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}</p>}
            {!match.winner && meta.result && status !== 'SCHEDULED' && <p className="text-xs text-amber-300">{meta.result}</p>}
            {match.winner && (
              <p className="flex items-center gap-2 text-sm font-bold text-emerald-400"><Trophy className="w-4 h-4" />{meta.result ?? `Winner: ${match.winner}`}</p>
            )}

            {open && closesIn !== null && (
              <p className="flex items-center gap-1.5 text-xs text-amber-400"><Clock className="w-3.5 h-3.5" />Betting closes in {closesIn >= 86400 ? `${Math.floor(closesIn / 86400)}d ${Math.floor((closesIn % 86400) / 3600)}h` : closesIn >= 3600 ? `${Math.floor(closesIn / 3600)}h ${Math.floor((closesIn % 3600) / 60)}m` : `${Math.floor(closesIn / 60)}:${String(closesIn % 60).padStart(2, '0')}`}</p>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(['HOME', 'AWAY'] as const).map((selection) => {
                const team = selection === 'HOME' ? match.home_team : match.away_team
                const odds = match.odds?.[selection]
                return (
                  <button key={selection} type="button" onClick={() => void handleBet(match, selection)} disabled={!open || placing === match.match_id} className="rounded-xl border border-dark-border bg-dark-elevated p-4 text-left transition hover:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">
                    <span className="block text-xs text-slate-400">Match winner</span>
                    <span className="mt-1 block font-bold text-white">{team}</span>
                    <span className="mt-2 block text-xs font-mono font-black text-emerald-400">
                      {placing === match.match_id ? 'Submitting…' : open ? `${odds ? odds.toFixed(2) : '—'}× payout` : 'Market closed'}
                    </span>
                  </button>
                )
              })}
            </div>

            {myPick && (
              <p className="text-xs text-slate-300">
                Your pick: <span className="font-bold">{myPick.team}</span> • {formatPaiseToRupee(myPick.stake)} @ {myPick.odds.toFixed(2)}× •{' '}
                <span className={`font-bold ${predictionPill[myPick.status] ?? ''}`}>{myPick.status === 'PLACED' ? 'Pending' : myPick.status}</span>
              </p>
            )}
          </article>
        )
      })}

      {mine.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-bold text-white">My recent predictions</h3>
          {mine.map((prediction) => (
            <div key={prediction.prediction_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-dark-card border border-dark-border p-3 text-xs">
              <span className="text-slate-300">{prediction.home_team} vs {prediction.away_team} • picked <span className="font-bold text-white">{prediction.team}</span></span>
              <span className="font-mono text-slate-400">{formatPaiseToRupee(prediction.stake)} @ {prediction.odds.toFixed(2)}×</span>
              <span className={`font-bold ${predictionPill[prediction.status] ?? ''}`}>
                {prediction.status === 'WON' ? `WON ${formatPaiseToRupee(prediction.payout)}` : prediction.status === 'PLACED' ? 'Pending' : prediction.status}
              </span>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
