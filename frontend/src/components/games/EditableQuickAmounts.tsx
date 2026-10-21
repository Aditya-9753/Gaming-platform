import React, { useState } from 'react'
import { Check, Pencil, RotateCcw } from 'lucide-react'
import { t as tr } from '../../i18n'

export interface EditableQuickAmountsProps {
  amounts: number[]
  onSave: (amounts: number[]) => void
  onReset: () => void
  onPick: (amount: number) => void
  selected?: number
  disabled?: boolean
  min: number
  max: number
  columns?: 2 | 3 | 4 | 5 | 6
  variant?: 'dark' | 'light'
}

const colClass = { 2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-4', 5: 'grid-cols-5', 6: 'grid-cols-6' }

export const EditableQuickAmounts: React.FC<EditableQuickAmountsProps> = ({
  amounts, onSave, onReset, onPick, selected, disabled = false, min, max, columns = 2, variant = 'dark',
}) => {
  const idle = variant === 'light'
    ? 'bg-slate-100 text-slate-600 border border-slate-200 hover:text-slate-900'
    : 'bg-dark-bg/70 text-slate-300 border border-dark-border hover:text-white'
  const active = variant === 'light' ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-dark-bg'
  const inputClass = variant === 'light' ? 'bg-white text-slate-800' : 'bg-dark-bg text-white'

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string[]>(amounts.map(String))

  const commit = () => {
    const next = draft.map((value, index) => {
      const n = Math.round(Number(value))
      return Number.isFinite(n) && n >= min ? Math.min(n, max) : amounts[index]
    })
    onSave(next)
    setEditing(false)
  }

  return (
    <div className="space-y-1.5">
      <div className={`grid ${colClass[columns]} gap-1.5`}>
        {amounts.map((amount, index) => editing ? (
          <input
            key={index}
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            value={draft[index]}
            onChange={(e) => setDraft((d) => d.map((v, i) => (i === index ? e.target.value : v)))}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit() } }}
            aria-label={`Quick amount ${index + 1}`}
            className={`w-full rounded-lg ${inputClass} border border-amber-500/60 px-1.5 py-1 text-center text-xs font-mono font-bold focus:outline-none`}
          />
        ) : (
          <button
            key={index}
            type="button"
            disabled={disabled}
            onClick={() => onPick(amount)}
            className={`rounded-lg px-1.5 py-1 text-xs font-bold transition disabled:opacity-50 ${
              selected === amount ? active : idle
            }`}
          >
            ₹{amount}
          </button>
        ))}
      </div>
      <div className="flex items-center justify-end gap-3 text-[11px]">
        {editing ? (
          <>
            <button type="button" onClick={() => { onReset(); setEditing(false) }} className="flex items-center gap-1 text-slate-400 hover:text-white"><RotateCcw className="w-3 h-3" />{tr('Reset')}</button>
            <button type="button" onClick={commit} className="flex items-center gap-1 font-bold text-emerald-400"><Check className="w-3 h-3" />{tr('Save')}</button>
          </>
        ) : (
          <button type="button" onClick={() => { setDraft(amounts.map(String)); setEditing(true) }} disabled={disabled} className="flex items-center gap-1 text-slate-400 hover:text-white disabled:opacity-40"><Pencil className="w-3 h-3" />{tr('Edit amounts')}</button>
        )}
      </div>
    </div>
  )
}
