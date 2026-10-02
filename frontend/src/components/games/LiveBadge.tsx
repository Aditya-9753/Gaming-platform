import React from 'react'

export interface LiveBadgeProps {
  playerCount?: number
  label?: string
}

export const LiveBadge: React.FC<LiveBadgeProps> = ({ playerCount, label = 'LIVE' }) => {
  return (
    <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 text-[10px] font-black uppercase tracking-wider">
      <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping shrink-0" />
      <span>{label}</span>
      {playerCount !== undefined && (
        <span className="text-slate-400 font-semibold normal-case ml-0.5">
          ({playerCount})
        </span>
      )}
    </div>
  )
}

