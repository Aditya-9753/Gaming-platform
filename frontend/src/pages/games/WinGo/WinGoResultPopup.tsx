import React, { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { WinGoBall } from './WinGoBall'
import { pickLabel, type WingoPick } from './wingoRules'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { playSound, playWinFor } from '../../../utils/sounds'
import type { WingoResult } from './useWingoRound'
import { t as tr } from '../../../i18n'

export interface SettledBet { pick: WingoPick; amountPaise: number; winPaise: number }

export interface WinGoResultPopupProps {
  result: WingoResult | null
  bets: SettledBet[]
  modeLabel: string
  onClose: () => void
}

const colourChip: Record<string, string> = { GREEN: 'bg-emerald-500', RED: 'bg-rose-500', VIOLET: 'bg-violet-500' }
const CONFETTI = ['#f43f5e', '#fbbf24', '#10b981', '#8b5cf6', '#38bdf8', '#fb923c']

/** Centred win / lose card shown when a period with your bets is drawn. */
export const WinGoResultPopup: React.FC<WinGoResultPopupProps> = ({ result, bets, modeLabel, onClose }) => {
  const [autoClose, setAutoClose] = useState(true)
  const totalWin = bets.reduce((s, b) => s + b.winPaise, 0)
  const totalStake = bets.reduce((s, b) => s + b.amountPaise, 0)
  const net = totalWin - totalStake
  const won = totalWin > 0

  // Win / lose sound once per drawn result
  useEffect(() => {
    if (!result) return
    if (won) playWinFor(totalWin, totalStake)
    else playSound('lose')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  useEffect(() => {
    if (!result || !autoClose) return
    const timer = setTimeout(onClose, 4500)
    return () => clearTimeout(timer)
  }, [result, autoClose, onClose])

  useEffect(() => {
    if (!result) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [result, onClose])

  const confetti = useMemo(() => Array.from({ length: 36 }, (_, i) => ({
    left: (i * 37) % 100,
    delay: (i % 9) * 0.12,
    duration: 1.8 + (i % 5) * 0.35,
    colour: CONFETTI[i % CONFETTI.length],
    size: 6 + (i % 3) * 3,
  })), [])

  if (!result) return null

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/65 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label={won ? 'You won' : 'You lost'}>
      {won && (
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          {confetti.map((c, i) => (
            <span key={i} className="absolute top-[-20px] rounded-sm animate-[confetti_2s_linear_infinite]" style={{ left: `${c.left}%`, width: c.size, height: c.size * 1.6, background: c.colour, animationDuration: `${c.duration}s`, animationDelay: `${c.delay}s` }} />
          ))}
        </div>
      )}

      <div className="relative w-full max-w-[22rem] animate-[popIn_0.35s_ease-out]" onClick={(e) => e.stopPropagation()}>
        <div className={`relative rounded-3xl px-5 pb-5 pt-14 text-center shadow-2xl ${won ? 'bg-gradient-to-b from-orange-400 to-rose-600' : 'bg-gradient-to-b from-slate-500 to-slate-700'}`}>
          <div className={`absolute left-1/2 top-0 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-4 border-white/80 text-5xl shadow-xl ${won ? 'bg-gradient-to-b from-amber-200 to-amber-500' : 'bg-gradient-to-b from-slate-200 to-slate-400'}`}>
            {won ? '🏆' : '😔'}
          </div>
          <h3 className="text-2xl font-black text-white sm:text-3xl">{won ? 'Congratulations!' : 'Better luck next time'}</h3>

          <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-xs text-white">
            <span>{tr('Result')}</span>
            <span className="flex overflow-hidden rounded-md">
              {result.colours.map((c) => <span key={c} className={`px-2 py-0.5 font-bold ${colourChip[c] ?? 'bg-slate-500'}`}>{c.charAt(0) + c.slice(1).toLowerCase()}</span>)}
            </span>
            <WinGoBall number={result.number} size={34} />
            <span className="rounded-md bg-white/25 px-2 py-0.5 font-bold">{result.size === 'BIG' ? 'Big' : 'Small'}</span>
          </div>

          <div className="mt-4 rounded-2xl bg-white px-4 py-4 shadow-inner">
            <p className={`text-sm font-bold ${won ? 'text-emerald-600' : 'text-rose-500'}`}>{won ? 'You won' : 'You lost'}</p>
            <p className={`text-4xl font-black ${won ? 'text-emerald-600' : 'text-rose-500'}`}>
              {won ? formatPaiseToRupee(totalWin) : formatPaiseToRupee(totalStake)}
            </p>
            {won && <p className="text-xs font-semibold text-slate-500">Net {net >= 0 ? '+' : '−'}{formatPaiseToRupee(Math.abs(net))}</p>}

            <div className="mt-3 max-h-36 space-y-1 overflow-y-auto border-t border-slate-100 pt-2 text-left text-xs">
              {bets.map((b, i) => (
                <div key={i} className="flex items-center justify-between gap-2">
                  <span className="text-slate-600">{b.pick.type === 'NUMBER' ? `Number ${b.pick.value}` : pickLabel(b.pick)} · {formatPaiseToRupee(b.amountPaise)}</span>
                  <span className={`font-bold ${b.winPaise ? 'text-emerald-600' : 'text-rose-400'}`}>{b.winPaise ? `+${formatPaiseToRupee(b.winPaise)}` : 'Lost'}</span>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-slate-400">{modeLabel} · <span className="font-mono">{result.period}</span></p>
          </div>

          <label className="mt-4 flex items-center justify-center gap-2 text-xs text-white/90">
            <input type="checkbox" checked={autoClose} onChange={(e) => setAutoClose(e.target.checked)} className="rounded" />
            {tr('Auto close')}
          </label>
        </div>
        <button type="button" onClick={onClose} aria-label={tr('Close')} className="mx-auto mt-4 flex h-10 w-10 items-center justify-center rounded-full border-2 border-white text-white"><X className="h-5 w-5" /></button>
      </div>
    </div>
  )
}
