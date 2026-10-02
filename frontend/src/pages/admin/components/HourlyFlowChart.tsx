import React, { useMemo, useState } from 'react'
import { formatPaiseToRupee } from '../../../utils/formatters'

export interface HourPoint { hour: string; wagered: number; paid: number; bets: number }

// Validated categorical slots 1-2 (dark), checked against the #11151d card surface
const SERIES = [
  { key: 'wagered' as const, label: 'Wagered', color: '#3987e5' },
  { key: 'paid' as const, label: 'Paid to players', color: '#d95926' },
]

const W = 640
const H = 220
const PAD = { top: 16, right: 92, bottom: 26, left: 56 }

const compact = (paise: number) => {
  const r = paise / 100
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(1)}L`
  if (r >= 1e3) return `₹${(r / 1e3).toFixed(1)}k`
  return `₹${Math.round(r)}`
}

/** Wagered vs paid per hour, one shared ₹ axis (never dual-axis). */
export const HourlyFlowChart: React.FC<{ data: HourPoint[]; onSelect?: (index: number) => void }> = ({ data, onSelect }) => {
  const [hover, setHover] = useState<number | null>(null)
  const [table, setTable] = useState(false)

  const { max, ticks } = useMemo(() => {
    const peak = Math.max(1, ...data.flatMap((d) => [d.wagered, d.paid]))
    const step = 10 ** Math.floor(Math.log10(peak))
    const nice = Math.ceil(peak / step) * step
    return { max: nice, ticks: [0, nice / 2, nice] }
  }, [data])

  if (data.length === 0) return <p className="text-sm text-slate-400">No activity yet.</p>
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const x = (i: number) => PAD.left + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW)
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH
  const path = (key: 'wagered' | 'paid') => data.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(' ')
  const last = data.length - 1
  const hovered = hover !== null ? data[hover] : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex gap-4" aria-label="Legend">
          {SERIES.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5 text-slate-300"><span className="h-0.5 w-4 rounded" style={{ background: s.color }} />{s.label}</span>
          ))}
        </div>
        <button type="button" onClick={() => setTable((t) => !t)} className="text-slate-400 hover:text-white">{table ? 'Show chart' : 'Show table'}</button>
      </div>

      {table ? (
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-slate-400"><th className="py-1">Hour (IST)</th><th className="py-1 text-right">Bets</th><th className="py-1 text-right">Wagered</th><th className="py-1 text-right">Paid</th></tr></thead>
            <tbody>
              {[...data].reverse().map((d) => (
                <tr key={d.hour} onClick={() => onSelect?.(data.indexOf(d))} className={`border-t border-dark-border/50 ${onSelect ? 'cursor-pointer hover:bg-dark-elevated/60' : ''}`}><td className="py-1 text-slate-300">{d.hour}</td><td className="py-1 text-right text-slate-300">{d.bets}</td><td className="py-1 text-right font-mono text-slate-200">{formatPaiseToRupee(d.wagered)}</td><td className="py-1 text-right font-mono text-slate-200">{formatPaiseToRupee(d.paid)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Wagered and paid per hour, last 24 hours">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="#252b37" strokeWidth={1} />
                <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="fill-slate-500" fontSize={10}>{compact(t)}</text>
              </g>
            ))}
            {data.map((d, i) => (i % 4 === 0 || i === last) && (
              <text key={d.hour + i} x={x(i)} y={H - 8} textAnchor="middle" className="fill-slate-500" fontSize={10}>{d.hour}</text>
            ))}
            {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} stroke="#64748b" strokeWidth={1} strokeDasharray="3 3" />}
            {SERIES.map((s) => (
              <g key={s.key}>
                <path d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                {/* direct label at the line end, in text ink with a colour swatch */}
                <circle cx={x(last)} cy={y(data[last][s.key])} r={4} fill={s.color} stroke="#11151d" strokeWidth={2} />
                <text x={x(last) + 8} y={y(data[last][s.key]) + 4} className="fill-slate-300" fontSize={10}>{s.label.split(' ')[0]} {compact(data[last][s.key])}</text>
              </g>
            ))}
            {hover !== null && SERIES.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(data[hover][s.key])} r={4} fill={s.color} stroke="#11151d" strokeWidth={2} />
            ))}
            {/* hit areas wider than the marks */}
            {data.map((_d, i) => (
              <rect key={i} x={x(i) - innerW / data.length / 2} y={PAD.top} width={innerW / data.length} height={innerH} fill="transparent"
                style={onSelect ? { cursor: 'pointer' } : undefined} onClick={() => onSelect?.(i)}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={-1} />
            ))}
          </svg>
          {hovered && hover !== null && (
            <div className="pointer-events-none absolute top-1 rounded-lg border border-dark-border bg-dark-elevated px-3 py-2 text-[11px] shadow-xl"
              style={{ left: `${Math.min(70, (x(hover) / W) * 100)}%` }}>
              <p className="font-bold text-white">{hovered.hour} · {hovered.bets} bets</p>
              {onSelect && <p className="text-slate-500">Click to see these bets</p>}
              {SERIES.map((s) => (
                <p key={s.key} className="flex items-center gap-1.5 text-slate-300"><span className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.label}: <span className="font-mono text-white">{formatPaiseToRupee(hovered[s.key])}</span></p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
