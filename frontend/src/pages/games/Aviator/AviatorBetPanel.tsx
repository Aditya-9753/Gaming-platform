import React, { useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import type { AviatorBetSlot } from './useAviatorBet'
import { EditableQuickAmounts, useQuickAmounts } from '../../../components/games/EditableQuickAmounts'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'
import { t as tr } from '../../../i18n'

type Phase = 'waiting' | 'betting' | 'flying' | 'crashed'

export interface AviatorBetPanelProps {
  slot: AviatorBetSlot
  phase: Phase
  multiplier: number
  roundId: string | null
  minRupees: number
  maxRupees: number
}

const DEFAULT_QUICK = [10, 50, 100, 500]

/** One bet box styled after the original game: amount stepper, quick chips, big action button. */
export const AviatorBetPanel: React.FC<AviatorBetPanelProps> = ({ slot, phase, multiplier, roundId, minRupees, maxRupees }) => {
  const [tab, setTab] = useState<'bet' | 'auto'>('bet')
  const [amount, setAmount] = useState(10)
  const [autoOn, setAutoOn] = useState(false)
  const [autoValue, setAutoValue] = useState('2.00')
  const quick = useQuickAmounts('gamezone.aviator.quickAmounts', DEFAULT_QUICK)

  const hasBet = slot.entryId !== null
  const betIsForThisRound = hasBet && slot.roundId === roundId
  const flying = phase === 'flying'
  const locked = hasBet || slot.busy
  const step = amount >= 100 ? 10 : 1
  const clamp = (n: number) => Math.min(maxRupees, Math.max(minRupees, Math.round(n)))

  const autoTarget = (() => {
    const parsed = parseFloat(autoValue)
    return autoOn && Number.isFinite(parsed) && parsed >= 1.01 ? Math.min(parsed, 100) : undefined
  })()

  let action: { label: string; sub?: string; className: string; onClick?: () => void; disabled?: boolean }
  if (slot.busy) {
    action = { label: 'Please wait…', className: 'bg-slate-600', disabled: true }
  } else if (hasBet && flying && betIsForThisRound) {
    action = {
      label: 'CASH OUT',
      sub: formatPaiseToRupee((slot.betPaise ?? 0) * multiplier),
      className: 'bg-gradient-to-b from-amber-400 to-orange-500 shadow-orange-500/40 animate-pulse',
      onClick: () => void slot.cashout(),
    }
  } else if (hasBet) {
    action = { label: 'WAITING', sub: 'for take-off', className: 'bg-gradient-to-b from-rose-500 to-rose-700', disabled: true }
  } else if (phase === 'betting') {
    action = {
      label: 'BET',
      sub: `₹${amount.toFixed(2)}`,
      className: 'bg-gradient-to-b from-emerald-400 to-emerald-600 shadow-emerald-500/30',
      onClick: () => void slot.place(rupeeToPaise(amount), autoTarget),
    }
  } else {
    action = { label: 'BET', sub: 'next round', className: 'bg-gradient-to-b from-emerald-700 to-emerald-900', disabled: true }
  }

  return (
    <div className="rounded-xl bg-[#1b1c1d] border border-white/5 p-2 space-y-2">
      <div className="flex justify-center">
        <div className="inline-flex rounded-full bg-black/40 p-0.5 text-[11px] font-bold">
          {(['bet', 'auto'] as const).map((t) => (
            <button key={t} type="button" onClick={() => setTab(t)} className={`px-4 py-0.5 rounded-full capitalize transition ${tab === t ? 'bg-[#2c2d30] text-white' : 'text-slate-400'}`}>{t}</button>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center rounded-full bg-black/50 px-1 py-0.5">
            <button type="button" aria-label={tr('Decrease')} disabled={locked} onClick={() => setAmount((a) => clamp(a - step))} className="w-6 h-6 rounded-full bg-[#2c2d30] text-slate-300 flex items-center justify-center disabled:opacity-40"><Minus className="w-3 h-3" /></button>
            <input
              type="number"
              inputMode="decimal"
              value={amount}
              disabled={locked}
              min={minRupees}
              max={maxRupees}
              onChange={(e) => setAmount(Number(e.target.value) || 0)}
              onBlur={() => setAmount((a) => clamp(a))}
              aria-label={tr('Bet amount in rupees')}
              className="flex-1 min-w-0 bg-transparent text-center font-mono font-black text-white text-sm focus:outline-none disabled:opacity-60"
            />
            <button type="button" aria-label={tr('Increase')} disabled={locked} onClick={() => setAmount((a) => clamp(a + step))} className="w-6 h-6 rounded-full bg-[#2c2d30] text-slate-300 flex items-center justify-center disabled:opacity-40"><Plus className="w-3 h-3" /></button>
          </div>
          <EditableQuickAmounts
            amounts={quick.amounts}
            onSave={quick.save}
            onReset={quick.reset}
            onPick={(n) => setAmount(clamp(n))}
            selected={amount}
            disabled={locked}
            min={minRupees}
            max={maxRupees}
            columns={4}
          />
        </div>

        <button
          type="button"
          onClick={action.onClick}
          disabled={action.disabled}
          className={`w-[36%] max-w-[160px] min-h-[64px] rounded-xl text-white shadow-lg flex flex-col items-center justify-center transition active:scale-[0.98] disabled:cursor-not-allowed ${action.className}`}
        >
          <span className="text-base font-black tracking-wide">{tr(action.label)}</span>
          {action.sub && <span className="text-xs font-mono font-bold opacity-90">{action.sub}</span>}
        </button>
      </div>

      {tab === 'auto' && (
        <div className="flex items-center justify-between gap-3 border-t border-white/5 pt-2 text-xs">
          <label className="flex items-center gap-2 text-slate-300 font-semibold cursor-pointer">
            <input type="checkbox" checked={autoOn} disabled={locked} onChange={(e) => setAutoOn(e.target.checked)} className="rounded" />
            {tr('Auto cash out')}
          </label>
          <div className="flex items-center rounded-full bg-black/50 px-3 py-1">
            <input
              type="number"
              step="0.1"
              min="1.01"
              max="100"
              value={autoValue}
              disabled={locked || !autoOn}
              onChange={(e) => setAutoValue(e.target.value)}
              aria-label={tr('Auto cash out multiplier')}
              className="w-16 bg-transparent text-right font-mono font-bold text-white focus:outline-none disabled:opacity-50"
            />
            <span className="ml-1 text-slate-400 font-bold">{tr('x')}</span>
          </div>
        </div>
      )}
      {hasBet && slot.autoCashout && <p className="text-center text-[11px] text-amber-400">Auto cash out at {slot.autoCashout.toFixed(2)}x</p>}
    </div>
  )
}
