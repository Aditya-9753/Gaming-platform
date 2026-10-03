import React from 'react'
import { Minus, Plus } from 'lucide-react'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { EditableQuickAmounts, useQuickAmounts } from '../../../components/games/EditableQuickAmounts'

export interface MinesControlsProps {
  betRupees: string
  setBetRupees: (v: string) => void
  mineCount: number
  setMineCount: (v: number) => void
  isPlaying: boolean
  onStart: () => void
  onCashout: () => void
  currentMultiplier: number
  nextMultiplier?: number | null
  canCashout?: boolean
  busy?: boolean
  potentialWinPaise: number
  gemsFound?: number
}

const MINE_PRESETS = [1, 3, 5, 10, 20, 24]

export const MinesControls: React.FC<MinesControlsProps> = ({
  betRupees,
  setBetRupees,
  mineCount,
  setMineCount,
  isPlaying,
  onStart,
  onCashout,
  currentMultiplier,
  nextMultiplier,
  canCashout = false,
  busy = false,
  potentialWinPaise,
  gemsFound = 0,
}) => {
  const quick = useQuickAmounts('gamezone.mines.quickAmounts', [10, 50, 100, 500])
  const amount = Number(betRupees) || 0
  const setAmount = (n: number) => setBetRupees(String(Math.max(1, Math.round(n))))

  return (
    <div className="space-y-3 sm:space-y-4 rounded-2xl sm:rounded-3xl border border-amber-400/30 bg-gradient-to-b from-[#2b0d3d] to-[#1a0826] p-3 sm:p-4 shadow-2xl">
      {isPlaying && (
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-black/30 py-2"><p className="text-[10px] uppercase tracking-wider text-violet-300">Gems</p><p className="font-black text-amber-300">{gemsFound}</p></div>
          <div className="rounded-xl bg-black/30 py-2"><p className="text-[10px] uppercase tracking-wider text-violet-300">Current</p><p className="font-mono font-black text-white">{currentMultiplier.toFixed(2)}x</p></div>
          <div className="rounded-xl bg-black/30 py-2"><p className="text-[10px] uppercase tracking-wider text-violet-300">Next gem</p><p className="font-mono font-black text-emerald-300">{nextMultiplier ? `${nextMultiplier.toFixed(2)}x` : '—'}</p></div>
        </div>
      )}

      {/* Settings are locked mid-game; on phones hide them so Cash Out stays right under the board */}
      <div className={`space-y-2 ${isPlaying ? 'hidden lg:block' : ''}`}>
        <label className="text-xs font-bold uppercase tracking-wider text-violet-200">Bet amount</label>
        <div className="flex items-center rounded-full bg-black/40 px-1 py-1">
          <button type="button" aria-label="Halve" disabled={isPlaying} onClick={() => setAmount(amount / 2)} className="w-9 h-8 rounded-full bg-white/10 text-xs font-bold text-white disabled:opacity-40">½</button>
          <button type="button" aria-label="Decrease" disabled={isPlaying} onClick={() => setAmount(amount - 1)} className="ml-1 w-8 h-8 rounded-full bg-white/10 text-white flex items-center justify-center disabled:opacity-40"><Minus className="w-3.5 h-3.5" /></button>
          <span className="ml-2 font-bold text-amber-300">₹</span>
          <input
            type="number"
            min="1"
            disabled={isPlaying}
            value={betRupees}
            onChange={(e) => setBetRupees(e.target.value)}
            aria-label="Bet amount in rupees"
            className="min-w-0 flex-1 bg-transparent text-center font-mono text-lg font-black text-white focus:outline-none disabled:opacity-60"
          />
          <button type="button" aria-label="Increase" disabled={isPlaying} onClick={() => setAmount(amount + 1)} className="mr-1 w-8 h-8 rounded-full bg-white/10 text-white flex items-center justify-center disabled:opacity-40"><Plus className="w-3.5 h-3.5" /></button>
          <button type="button" aria-label="Double" disabled={isPlaying} onClick={() => setAmount(amount * 2)} className="w-9 h-8 rounded-full bg-white/10 text-xs font-bold text-white disabled:opacity-40">2×</button>
        </div>
        <EditableQuickAmounts
          amounts={quick.amounts}
          onSave={quick.save}
          onReset={quick.reset}
          onPick={setAmount}
          selected={amount}
          disabled={isPlaying}
          min={1}
          max={100000}
          columns={4}
        />
      </div>

      <div className={`space-y-2 ${isPlaying ? 'hidden lg:block' : ''}`}>
        <label className="text-xs font-bold uppercase tracking-wider text-violet-200">Mines: <span className="text-rose-300">{mineCount}</span></label>
        <div className="grid grid-cols-6 gap-1.5">
          {MINE_PRESETS.map((n) => (
            <button key={n} type="button" disabled={isPlaying} onClick={() => setMineCount(n)} className={`rounded-lg py-1.5 text-xs font-black transition disabled:opacity-50 ${mineCount === n ? 'bg-gradient-to-b from-rose-500 to-red-600 text-white shadow' : 'bg-black/40 text-violet-200'}`}>{n}</button>
          ))}
        </div>
        <input type="range" min={1} max={24} value={mineCount} disabled={isPlaying} onChange={(e) => setMineCount(Number(e.target.value))} aria-label="Number of mines" className="w-full accent-rose-500 disabled:opacity-50" />
      </div>

      {isPlaying ? (
        <button
          type="button"
          onClick={onCashout}
          disabled={!canCashout || busy}
          className="w-full rounded-2xl bg-gradient-to-b from-amber-300 to-orange-500 py-3.5 text-base font-black text-[#3b0f00] shadow-[0_6px_0_#9a3412] transition active:translate-y-1 active:shadow-[0_2px_0_#9a3412] disabled:opacity-50 disabled:shadow-none"
        >
          {canCashout ? `CASH OUT ${formatPaiseToRupee(potentialWinPaise)}` : 'Pick a tile to start winning'}
        </button>
      ) : (
        <button
          type="button"
          onClick={onStart}
          disabled={busy}
          className="w-full rounded-2xl bg-gradient-to-b from-emerald-400 to-emerald-600 py-3.5 text-base font-black text-white shadow-[0_6px_0_#065f46] transition active:translate-y-1 active:shadow-[0_2px_0_#065f46] disabled:opacity-50"
        >
          {busy ? 'Starting…' : `PLAY ₹${amount || 0}`}
        </button>
      )}
    </div>
  )
}
