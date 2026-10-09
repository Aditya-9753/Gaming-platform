import React, { useState } from 'react'
import { Button } from '../common/Button'
import { formatPaiseToRupee, rupeeToPaise } from '../../utils/formatters'
import { QUICK_BET_AMOUNTS } from '../../utils/constants'
import { t as tr } from '../../i18n'

export interface BetPanelProps {
  onPlaceBet: (amountPaise: number, autoCashout?: number) => void
  onCashout?: () => void
  disabled?: boolean
  isBetPlaced?: boolean
  currentMultiplier?: number
  minBetRupees?: number
  maxBetRupees?: number
  showAutoCashout?: boolean
  /** When set, shows a disabled status button instead of BET (e.g. bet already placed). */
  statusLabel?: string
}

export const BetPanel: React.FC<BetPanelProps> = ({
  onPlaceBet,
  onCashout,
  disabled = false,
  isBetPlaced = false,
  currentMultiplier = 1.0,
  minBetRupees = 10,
  maxBetRupees = 10000,
  showAutoCashout = true,
  statusLabel,
}) => {
  const [amountRupees, setAmountRupees] = useState<number>(minBetRupees)
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [autoCashout, setAutoCashout] = useState<string>('2.00')

  const handleDouble = () => {
    setAmountRupees((prev) => Math.min(prev * 2, maxBetRupees))
  }

  const handleHalf = () => {
    setAmountRupees((prev) => Math.max(Math.floor(prev / 2), minBetRupees))
  }

  const handleQuickBet = (amt: number) => {
    setAmountRupees(amt)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (isBetPlaced) {
      onCashout?.()
    } else {
      const parsed = parseFloat(autoCashout)
      const autoVal = showAutoCashout && autoEnabled && Number.isFinite(parsed) && parsed >= 1.01 ? parsed : undefined
      onPlaceBet(rupeeToPaise(amountRupees), autoVal)
    }
  }

  const potentialWinPaise = rupeeToPaise(amountRupees) * currentMultiplier

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-3"
    >
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>Bet Amount (INR)</span>
        <span>
          Min: ₹{minBetRupees} • Max: ₹{maxBetRupees}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleHalf}
          disabled={disabled || isBetPlaced}
          className="px-3 py-2 rounded-xl bg-dark-elevated text-xs font-bold text-slate-300 hover:text-white border border-dark-border disabled:opacity-50"
        >
          ½
        </button>

        <div className="relative flex-1">
          <span className="absolute left-3 top-2.5 text-sm font-bold text-emerald-400">₹</span>
          <input
            type="number"
            min={minBetRupees}
            max={maxBetRupees}
            value={amountRupees}
            disabled={disabled || isBetPlaced}
            onChange={(e) => setAmountRupees(Number(e.target.value) || 0)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl pl-8 pr-3 py-2 text-sm font-mono font-bold text-white focus:outline-none focus:border-emerald-500"
          />
        </div>

        <button
          type="button"
          onClick={handleDouble}
          disabled={disabled || isBetPlaced}
          className="px-3 py-2 rounded-xl bg-dark-elevated text-xs font-bold text-slate-300 hover:text-white border border-dark-border disabled:opacity-50"
        >
          2×
        </button>
      </div>

      {/* Quick Bet Buttons */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        {QUICK_BET_AMOUNTS.slice(0, 5).map((amt) => (
          <button
            key={amt}
            type="button"
            disabled={disabled || isBetPlaced}
            onClick={() => handleQuickBet(amt)}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all shrink-0 ${
              amountRupees === amt
                ? 'bg-emerald-500 text-dark-bg'
                : 'bg-dark-elevated text-slate-400 hover:text-white border border-dark-border'
            }`}
          >
            ₹{amt}
          </button>
        ))}
      </div>

      {/* Auto Cashout */}
      {showAutoCashout && (
        <div className="flex items-center justify-between gap-3 pt-1 text-xs">
          <label className="flex items-center gap-2 text-slate-400 font-semibold shrink-0 cursor-pointer">
            <input
              type="checkbox"
              checked={autoEnabled}
              disabled={disabled || isBetPlaced}
              onChange={(e) => setAutoEnabled(e.target.checked)}
              className="rounded"
            />
            {tr('Auto Cashout')}
          </label>
          <div className="relative w-28">
            <input
              type="number"
              step="0.1"
              min="1.01"
              max="100"
              value={autoCashout}
              disabled={disabled || isBetPlaced || !autoEnabled}
              onChange={(e) => setAutoCashout(e.target.value)}
              className="w-full bg-dark-elevated border border-dark-border rounded-lg px-2 py-1 text-right text-xs font-mono font-bold text-white focus:outline-none focus:border-emerald-500 pr-5"
            />
            <span className="absolute right-2 top-1 text-slate-400 font-bold">×</span>
          </div>
        </div>
      )}

      {/* Action Button */}
      {statusLabel ? (
        <Button type="button" variant="secondary" disabled className="w-full py-3.5 text-base font-black">
          {statusLabel}
        </Button>
      ) : isBetPlaced ? (
        <Button
          type="submit"
          variant="accent"
          className="w-full py-3.5 text-base font-black shadow-lg shadow-purple-500/30 animate-pulse"
        >
          CASHOUT ({formatPaiseToRupee(potentialWinPaise)})
        </Button>
      ) : (
        <Button
          type="submit"
          variant="primary"
          disabled={disabled || amountRupees < minBetRupees}
          className="w-full py-3.5 text-base font-black"
        >
          BET ₹{amountRupees}
        </Button>
      )}
    </form>
  )
}

