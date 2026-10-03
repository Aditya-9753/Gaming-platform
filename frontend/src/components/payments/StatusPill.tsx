import React from 'react'

/** User-facing payment status: PENDING (amber), SUCCESS / COMPLETED (green), REJECTED (red). */
export const StatusPill: React.FC<{ status: string }> = ({ status }) => {
  const tone = status === 'SUCCESS' || status === 'COMPLETED' || status === 'ACTIVE' || status === 'MATCHED'
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    : status === 'REJECTED' || status === 'DISABLED' || status === 'IGNORED'
      ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
      : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
  return <span className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-black tracking-wide ${tone}`}>{status.replace('_', ' ')}</span>
}
