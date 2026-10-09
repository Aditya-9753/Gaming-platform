import React from 'react'
import { t as tr } from '../../../i18n'

const SUIT: Record<string, { symbol: string; red: boolean }> = {
  S: { symbol: '♠', red: false },
  H: { symbol: '♥', red: true },
  D: { symbol: '♦', red: true },
  C: { symbol: '♣', red: false },
}

/** Card code like "AS" / "TH" (T = 10). `code` null = face down. */
export const PlayingCard: React.FC<{ code: string | null; delayMs?: number; highlight?: boolean }> = ({ code, delayMs = 0, highlight = false }) => {
  if (!code) {
    return (
      <div className="flex aspect-[5/7] w-[clamp(44px,13vw,72px)] items-center justify-center rounded-lg border-2 border-white/80 bg-[repeating-linear-gradient(45deg,#7f1d1d_0_6px,#991b1b_6px_12px)] shadow-lg">
        <span className="text-lg font-black italic text-amber-300/90">{tr('R')}</span>
      </div>
    )
  }
  const rank = code[0] === 'T' ? '10' : code[0]
  const suit = SUIT[code[1]] ?? SUIT.S
  return (
    <div
      className={`relative aspect-[5/7] w-[clamp(44px,13vw,72px)] rounded-lg bg-white shadow-lg animate-[popIn_0.45s_ease-out_both] ${highlight ? 'ring-2 ring-amber-300' : ''} ${suit.red ? 'text-red-600' : 'text-slate-900'}`}
      style={{ animationDelay: `${delayMs}ms` }}
      aria-label={`${rank} of ${{ S: 'spades', H: 'hearts', D: 'diamonds', C: 'clubs' }[code[1]] ?? ''}`}
    >
      <span className="absolute left-1 top-0.5 text-[clamp(11px,3vw,16px)] font-black leading-none">{rank}<br />{suit.symbol}</span>
      <span className="absolute inset-0 flex items-center justify-center text-[clamp(20px,6vw,34px)]">{suit.symbol}</span>
    </div>
  )
}
