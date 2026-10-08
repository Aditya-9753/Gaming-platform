import React, { useMemo, useState } from 'react'
import { cx } from './ui'

export interface ChartSeries {
  key: string
  label: string
  color: string
  /** 'usd' series use the right axis; counts use the left axis (never mixed on one scale). */
  axis: 'count' | 'usd'
}

interface Props {
  points: Array<Record<string, string | number>>
  xKey: string
  series: ChartSeries[]
  height?: number
  formatX?: (value: string) => string
}

const niceMax = (value: number) => {
  if (value <= 0) return 1
  const exp = Math.pow(10, Math.floor(Math.log10(value)))
  const n = value / exp
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * exp
}

/** Daily line chart with counts on the left axis and dollars (incl. negatives) on the right; legend chips toggle series. */
export const DualAxisChart: React.FC<Props> = ({ points, xKey, series, height = 240, formatX }) => {
  const [hidden, setHidden] = useState<Record<string, boolean>>({})
  const [hover, setHover] = useState<number | null>(null)
  const width = 720
  const pad = { l: 40, r: 56, t: 12, b: 26 }
  const plotW = width - pad.l - pad.r
  const plotH = height - pad.t - pad.b
  const visible = series.filter((s) => !hidden[s.key])

  const scales = useMemo(() => {
    const vals = (axis: 'count' | 'usd') => visible.filter((s) => s.axis === axis).flatMap((s) => points.map((p) => Number(p[s.key]) || 0))
    const counts = vals('count')
    const money = vals('usd')
    const cMax = niceMax(Math.max(0, ...counts))
    const uMaxRaw = Math.max(0, ...money)
    const uMinRaw = Math.min(0, ...money)
    const uMax = uMaxRaw > 0 ? niceMax(uMaxRaw) : 0
    const uMin = uMinRaw < 0 ? -niceMax(-uMinRaw) : 0
    return { cMax, uMax: uMax === uMin ? 1 : uMax, uMin }
  }, [points, visible])

  const x = (i: number) => pad.l + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW)
  const y = (v: number, axis: 'count' | 'usd') =>
    axis === 'count'
      ? pad.t + plotH - (v / scales.cMax) * plotH
      : pad.t + plotH - ((v - scales.uMin) / (scales.uMax - scales.uMin)) * plotH
  const zeroUsd = y(0, 'usd')
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  const labelEvery = Math.max(1, Math.ceil(points.length / 7))

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {series.map((s) => (
          <button key={s.key} type="button" onClick={() => setHidden((h) => ({ ...h, [s.key]: !h[s.key] }))} aria-pressed={!hidden[s.key]}
            className={cx('flex min-h-[32px] items-center gap-1.5 rounded-full border px-3 text-[11px] font-bold transition',
              hidden[s.key] ? 'border-dark-border text-slate-500' : 'border-transparent bg-dark-elevated text-white')}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: hidden[s.key] ? '#475569' : s.color }} />
            {s.label}
          </button>
        ))}
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Daily statistics chart"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
            const px = ((e.clientX - rect.left) / rect.width) * width
            const i = Math.round(((px - pad.l) / plotW) * (points.length - 1))
            setHover(points.length ? Math.max(0, Math.min(points.length - 1, i)) : null)
          }}>
          {ticks.map((t) => {
            const yy = pad.t + plotH - t * plotH
            return (
              <g key={t}>
                <line x1={pad.l} x2={width - pad.r} y1={yy} y2={yy} stroke="currentColor" className="text-slate-700/50" strokeDasharray="3 4" />
                <text x={pad.l - 6} y={yy + 3} textAnchor="end" className="fill-slate-500 text-[10px]">{Math.round(scales.cMax * t)}</text>
                <text x={width - pad.r + 6} y={yy + 3} className="fill-slate-500 text-[10px]">
                  {Math.round(scales.uMin + (scales.uMax - scales.uMin) * t)}$
                </text>
              </g>
            )
          })}
          {scales.uMin < 0 && <line x1={pad.l} x2={width - pad.r} y1={zeroUsd} y2={zeroUsd} stroke="#64748b" strokeWidth={1} />}
          {visible.map((s) => {
            const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(Number(p[s.key]) || 0, s.axis).toFixed(1)}`).join(' ')
            return <path key={s.key} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          })}
          {points.map((p, i) => i % labelEvery === 0 && (
            <text key={i} x={x(i)} y={height - 6} textAnchor="middle" className="fill-slate-500 text-[10px]">
              {formatX ? formatX(String(p[xKey])) : String(p[xKey])}
            </text>
          ))}
          {hover !== null && points[hover] && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + plotH} stroke="#94a3b8" strokeDasharray="2 3" />
              {visible.map((s) => (
                <circle key={s.key} cx={x(hover)} cy={y(Number(points[hover][s.key]) || 0, s.axis)} r={3.5} fill={s.color} />
              ))}
            </g>
          )}
        </svg>
        {hover !== null && points[hover] && (
          <div className="pointer-events-none absolute top-2 rounded-xl border border-dark-border bg-dark-bg/95 p-2.5 text-[11px] shadow-xl"
            style={{ left: `${Math.min(70, (x(hover) / width) * 100)}%` }}>
            <div className="mb-1 font-bold text-white">{formatX ? formatX(String(points[hover][xKey])) : String(points[hover][xKey])}</div>
            {series.map((s) => (
              <div key={s.key} className="flex items-center justify-between gap-4 text-slate-300">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.label}</span>
                <span className="font-bold tabular-nums text-white">
                  {s.axis === 'usd' ? `${Number(points[hover][s.key]).toFixed(2)} $` : points[hover][s.key]}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
