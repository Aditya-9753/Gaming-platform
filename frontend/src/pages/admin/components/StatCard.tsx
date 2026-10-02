import React from 'react'

export interface StatCardProps {
  label: string
  value: string | number
  change?: string
  isPositive?: boolean
  icon: React.ReactNode
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  change,
  isPositive = true,
  icon,
}) => {
  return (
    <div className="p-5 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{label}</span>
        <div className="w-9 h-9 rounded-xl bg-dark-elevated border border-dark-border flex items-center justify-center text-slate-300">
          {icon}
        </div>
      </div>

      <div className="flex items-baseline justify-between">
        <div className="text-2xl font-black font-mono text-white">{value}</div>
        {change && (
          <span
            className={`text-xs font-bold ${
              isPositive ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {isPositive ? '↑' : '↓'} {change}
          </span>
        )}
      </div>
    </div>
  )
}

