import React, { useState } from 'react'
import { Ticket } from 'lucide-react'
import confetti from 'canvas-confetti'
import { Button } from '../common/Button'
import { showToast } from '../common/toastBus'
import { syncWalletBalance, walletApi } from '../../services/wallet.api'
import { getApiErrorMessage } from '../../utils/apiError'
import { t as tr } from '../../i18n'

/** Bonuses come only from promo codes (no automatic sign-up bonus); each code works once per player. */
export const PromoCodeCard: React.FC<{ onRedeemed?: () => void }> = ({ onRedeemed }) => {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const redeem = async (event: React.FormEvent) => {
    event.preventDefault()
    if (code.trim().length < 3) return
    setBusy(true)
    setError(null)
    try {
      const result = await walletApi.redeemPromo(code)
      await syncWalletBalance().catch(() => undefined)
      confetti({ particleCount: 70, spread: 60, origin: { y: 0.7 } })
      showToast({ title: tr('Promo bonus added'), message: `₹${(result.amount_paise / 100).toLocaleString('en-IN')} ${tr('from code')} ${result.code}`, type: 'success' })
      setCode('')
      onRedeemed?.()
    } catch (err) {
      setError(getApiErrorMessage(err, tr('This promo code could not be used.')))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={redeem} className="rounded-2xl border border-amber-500/20 bg-gradient-to-r from-amber-950/30 via-dark-card to-dark-card p-5 shadow-xl">
      <div className="flex items-center gap-2 text-xs font-bold text-amber-300">
        <Ticket className="h-4 w-4" />{tr('Have a promo code?')}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={code} onChange={(e) => { setCode(e.target.value.toUpperCase().replace(/\s/g, '')); setError(null) }}
          maxLength={32} placeholder={tr('Enter code')} aria-label={tr('Promo code')} autoCapitalize="characters"
          className="min-w-0 flex-1 rounded-xl border border-dark-border bg-dark-elevated px-3 py-2.5 text-sm font-bold tracking-wider text-white placeholder:font-normal placeholder:tracking-normal placeholder:text-slate-500 focus:border-amber-400 focus:outline-none"
        />
        <Button type="submit" variant="accent" size="sm" isLoading={busy} disabled={code.trim().length < 3} className="shrink-0 font-black">{tr('Apply')}</Button>
      </div>
      {error && <p className="mt-2 text-xs font-medium text-rose-400">{error}</p>}
    </form>
  )
}
