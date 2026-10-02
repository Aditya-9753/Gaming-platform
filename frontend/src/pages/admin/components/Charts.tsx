import React from 'react'

export interface ChartDataPoint {
  label: string
  value: number
}

export interface AreaChartProps {
  data: ChartDataPoint[]
  height?: number
  color?: string
}

export const AreaChart: React.FC<AreaChartProps> = ({
  data,
  height = 180,
  color = '#10b981',
}) => {
  if (data.length === 0) return null

  const values = data.map((d) => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values) || 1
  const range = max - min || 1

  const width = 600
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((d.value - min) / range) * (height - 30) - 15
    return `${x},${y}`
  })

  const pathD = `M ${points.join(' L ')}`
  const areaD = `M 0,${height} L ${points.join(' L ')} L ${width},${height} Z`

  return (
    <div className="w-full overflow-hidden">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        <path d={areaD} fill="url(#areaGrad)" />
        <path d={pathD} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />

        {data.map((_, i) => {
          const [cx, cy] = points[i].split(',')
          return (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r="4"
              fill="#0b0e14"
              stroke={color}
              strokeWidth="2"
            />
          )
        })}
      </svg>

      <div className="flex items-center justify-between text-[10px] text-slate-500 mt-2 px-1 font-mono">
        {data.map((d, i) => (
          <span key={i}>{d.label}</span>
        ))}
      </div>
    </div>
  )
}
