import React, { useEffect, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { EditableQuickAmounts, useQuickAmounts } from '../../../components/games/EditableQuickAmounts'
import { pickLabel, pickTheme, type WingoPick } from './wingoRules'

export const QUANTITY_MULTIPLIERS = [1, 5, 10, 20, 50, 100]

export interface WinGoBetSheetProps {
  open: boolean
  pick: WingoPick | null
  modeLabel: string
  multiplier: number
  onMultiplier: (m: number) => void
  locked: boolean
  busy: boolean
  minRupees: number
  maxRupees: number
  onClose: () => void
  onConfirm: (totalRupees: number) => void
}

/** Bottom sheet: base amount x quantity, like popular WinGo games. */
export const WinGoBetSheet: React.FC<WinGoBetSheetProps> = ({
  open, pick, modeLabel, multiplier, onMultiplier, locked, busy, minRupees, maxRupees, onClose, onConfirm,
}) => {
  const quick = useQuickAmounts('gamezone.wingo.baseAmounts', [1, 10, 100, 1000])
  const [base, setBase] = useState(quick.amounts[0])
  const [quantity, setQuantity] = useState(multiplier)
  const [agree, setAgree] = useState(true)

  useEffect(() => { setQuantity(multiplier) }, [multiplier, open])
  useEffect(() => { if (open && locked) onClose() }, [locked, open, onClose])

  if (!open || !pick) return null
  const total = base * quantity
  const tooLow = total < minRupees
  const tooHigh = total > maxRupees

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-lg rounded-t-3xl bg-white overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className={`bg-gradient-to-r ${pickTheme(pick)} px-5 pt-4 pb-6 text-center text-white`}>
          <p className="text-lg font-black">{modeLabel}</p>
          <p className="mt-2 inline-block rounded-lg bg-white px-5 py-1 text-sm font-bold text-slate-800">Select&nbsp;&nbsp;{pickLabel(pick)}</p>
        </div>

        <div className="space-y-4 px-5 py-4 text-slate-700">
          <div className="flex items-start justify-between gap-4">
            <span className="pt-1 text-sm font-semibold">Balance</span>
            <div className="w-56">
              <EditableQuickAmounts
                amounts={quick.amounts}
                onSave={quick.save}
                onReset={quick.reset}
                onPick={setBase}
                selected={base}
                min={1}
                max={maxRupees}
                columns={4}
                variant="light"
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-4">
            <span className="text-sm font-semibold">Quantity</span>
            <div className="flex items-center gap-2">
              <button type="button" aria-label="Decrease quantity" onClick={() => setQuantity((q) => Math.max(1, q - 1))} className="w-8 h-8 rounded-lg bg-rose-500 text-white flex items-center justify-center"><Minus className="w-4 h-4" /></button>
              <input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Math.max(1, Math.round(Number(e.target.value)) || 1))} aria-label="Quantity" className="w-16 rounded-lg border border-slate-300 bg-white py-1 text-center font-bold text-slate-800 [color-scheme:light]" />
              <button type="button" aria-label="Increase quantity" onClick={() => setQuantity((q) => q + 1)} className="w-8 h-8 rounded-lg bg-rose-500 text-white flex items-center justify-center"><Plus className="w-4 h-4" /></button>
            </div>
          </div>

          <div className="flex flex-wrap justify-end gap-1.5">
            {QUANTITY_MULTIPLIERS.map((m) => (
              <button key={m} type="button" onClick={() => { setQuantity(m); onMultiplier(m) }} className={`rounded-lg px-3 py-1 text-xs font-bold ${quantity === m ? 'bg-rose-500 text-white' : 'bg-slate-100 text-slate-600'}`}>X{m}</button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-500">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="rounded" />
            I agree to the <span className="text-rose-500">game rules</span> (virtual credits only)
          </label>
          {(tooLow || tooHigh) && <p className="text-xs text-rose-500">Total must be between ₹{minRupees} and ₹{maxRupees}.</p>}
        </div>

        <div className="grid grid-cols-[1fr_2fr]">
          <button type="button" onClick={onClose} className="bg-slate-100 py-4 text-sm font-bold text-slate-500">Cancel</button>
          <button
            type="button"
            disabled={!agree || busy || locked || tooLow || tooHigh}
            onClick={() => onConfirm(total)}
            className={`bg-gradient-to-r ${pickTheme(pick)} py-4 text-sm font-black text-white disabled:opacity-50`}
          >
            {busy ? 'Placing…' : `Total amount ₹${total.toFixed(2)}`}
          </button>
        </div>
      </div>
    </div>
  )
}
