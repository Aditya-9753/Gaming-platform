import React, { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { MyBetsHistory } from '../../../components/games/MyBetsHistory'
import { numberColours } from './wingoRules'
import type { WingoResult } from './useWingoRound'
import { t as tr } from '../../../i18n'

interface RoundRow { period: string; number: number; size: string; colours: string[] }

interface ApiRound { result?: { period?: string; number?: number; size?: string; colours?: string[] } }

const dot: Record<string, string> = { GREEN: 'bg-emerald-500', RED: 'bg-rose-500', VIOLET: 'bg-violet-500' }
const numberText = (n: number) => {
  const c = numberColours(n)
  if (c.includes('VIOLET')) {
    return c[0] === 'RED'
      ? 'bg-gradient-to-b from-rose-500 to-violet-500 bg-clip-text text-transparent'
      : 'bg-gradient-to-b from-emerald-500 to-violet-500 bg-clip-text text-transparent'
  }
  return c[0] === 'RED' ? 'text-rose-500' : 'text-emerald-500'
}

const PAGE = 10

export interface WinGoHistoryTabsProps {
  gameId: string
  /** Latest live result, prepended without refetching. */
  latest: WingoResult | null
  myHistoryKey: number
  onRecent?: (numbers: number[]) => void
}

export const WinGoHistoryTabs: React.FC<WinGoHistoryTabsProps> = ({ gameId, latest, myHistoryKey, onRecent }) => {
  const [tab, setTab] = useState<'game' | 'chart' | 'mine'>('game')
  const [rows, setRows] = useState<RoundRow[]>([])
  const [page, setPage] = useState(1)

  useEffect(() => {
    setRows([])
    setPage(1)
    apiClient.get<ApiRound[]>(`/games/${gameId}/history`, { params: { limit: 100 } })
      .then(({ data }) => setRows(data.flatMap((r) => (r.result && typeof r.result.number === 'number'
        ? [{ period: r.result.period ?? '', number: r.result.number, size: r.result.size ?? '', colours: r.result.colours ?? [] }]
        : []))))
      .catch(() => undefined)
  }, [gameId])

  useEffect(() => {
    if (!latest) return
    setRows((items) => (items.some((r) => r.period === latest.period)
      ? items
      : [{ period: latest.period, number: latest.number, size: latest.size, colours: latest.colours }, ...items].slice(0, 100)))
  }, [latest])

  useEffect(() => { onRecent?.(rows.slice(0, 5).map((r) => r.number)) }, [rows, onRecent])

  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const visible = rows.slice((page - 1) * PAGE, page * PAGE)
  const tabs = [['game', 'Game history'], ['chart', 'Chart'], ['mine', 'My history']] as const

  return (
    <section className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" onClick={() => setTab(key)} className={`rounded-xl py-2.5 text-sm font-bold transition ${tab === key ? 'bg-gradient-to-r from-rose-500 to-orange-400 text-white shadow' : 'bg-white text-slate-500'}`}>{tr(label)}</button>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
        {tab === 'game' && (
          <>
            <table className="w-full text-sm">
              <thead className="bg-gradient-to-r from-rose-500 to-orange-400 text-white">
                <tr><th className="py-2.5 font-semibold">{tr('Period')}</th><th className="py-2.5 font-semibold">{tr('Number')}</th><th className="py-2.5 font-semibold">{tr('Big Small')}</th><th className="py-2.5 font-semibold">{tr('Color')}</th></tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.period} className="border-b border-slate-100 text-center">
                    <td className="py-2.5 font-mono text-xs text-slate-600">{r.period}</td>
                    <td className={`py-2.5 text-2xl font-black ${numberText(r.number)}`}>{r.number}</td>
                    <td className="py-2.5 text-slate-600">{r.size === 'BIG' ? 'Big' : 'Small'}</td>
                    <td className="py-2.5"><span className="inline-flex gap-1">{r.colours.map((c) => <span key={c} className={`w-3 h-3 rounded-full ${dot[c]}`} />)}</span></td>
                  </tr>
                ))}
                {visible.length === 0 && <tr><td colSpan={4} className="py-8 text-center text-xs text-slate-400">{tr('No results yet — the first period is running.')}</td></tr>}
              </tbody>
            </table>
            {pages > 1 && (
              <div className="flex items-center justify-center gap-4 py-3 text-sm text-slate-500">
                <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-rose-500 p-1.5 text-white disabled:bg-slate-200"><ChevronLeft className="w-4 h-4" /></button>
                <span>{page}/{pages}</span>
                <button type="button" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-rose-500 p-1.5 text-white disabled:bg-slate-200"><ChevronRight className="w-4 h-4" /></button>
              </div>
            )}
          </>
        )}

        {tab === 'chart' && (
          <div className="overflow-x-auto p-3">
            <p className="mb-2 text-xs text-slate-500">Last {Math.min(rows.length, 30)} periods — winning number per row</p>
            <table className="w-full text-xs">
              <tbody>
                {rows.slice(0, 30).map((r) => (
                  <tr key={r.period} className="border-b border-slate-100">
                    <td className="py-1 pr-2 font-mono text-[10px] text-slate-500">{r.period.slice(-5)}</td>
                    {Array.from({ length: 10 }, (_, n) => (
                      <td key={n} className="py-1 text-center">
                        <span className={`inline-flex w-5 h-5 items-center justify-center rounded-full text-[10px] font-bold ${n === r.number ? `${numberColours(n)[0] === 'RED' ? 'bg-rose-500' : 'bg-emerald-500'} text-white` : 'text-slate-300 border border-slate-200'}`}>{n}</span>
                      </td>
                    ))}
                    <td className="py-1 pl-2 text-center"><span className={`rounded px-1.5 py-0.5 text-[10px] font-bold text-white ${r.size === 'BIG' ? 'bg-orange-400' : 'bg-sky-500'}`}>{r.size === 'BIG' ? 'B' : 'S'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'mine' && (
          <div className="bg-dark-card p-3">
            <MyBetsHistory gameId={gameId} refreshKey={myHistoryKey} />
          </div>
        )}
      </div>
    </section>
  )
}
