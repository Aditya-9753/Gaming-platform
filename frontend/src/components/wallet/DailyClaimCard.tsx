import React, { useState } from 'react'
import { Gift, Sparkles, Check } from 'lucide-react'
import { Button } from '../common/Button'
import { useWalletStore } from '../../store/wallet.store'
import { walletApi } from '../../services/wallet.api'
import { showToast } from '../common/Toast'
import confetti from 'canvas-confetti'

export const DailyClaimCard: React.FC = () => {
  const { balance, setBalance } = useWalletStore()
  const dailyClaimAvailable = balance.dailyClaimAvailable
  const [isClaiming, setIsClaiming] = useState(false)

  const handleClaim = async () => {
    setIsClaiming(true)
    try {
      const result = await walletApi.claimDailyBonus()
      setBalance({ ...result.newBalance, dailyClaimAvailable: false, lastClaimDate: new Date().toISOString() })
      confetti({ particleCount: 70, spread: 60, origin: { y: 0.7 } })
      showToast({
        title: 'Daily credits claimed',
        message: `${(result.amountPaise / 100).toFixed(2)} credits were added by the server.`,
        type: 'success',
      })
    } catch {
      showToast({ title: 'Claim unavailable', message: 'The daily claim could not be processed. It may already have been claimed today.', type: 'error' })
    } finally {
      setIsClaiming(false)
    }
  }

  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-purple-950/40 via-dark-card to-dark-card border border-purple-500/20 p-5 shadow-xl flex items-center justify-between gap-4">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shrink-0">
          <Gift className="w-6 h-6" />
        </div>
        <div>
          <div className="flex items-center gap-1.5 text-xs font-bold text-purple-400">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Daily Free Bonus</span>
          </div>
          <h4 className="text-base font-black text-white mt-0.5">Claim ₹10 Free Everyday</h4>
          <p className="text-xs text-slate-400">
            Login every 24 hours to boost your wallet risk-free.
          </p>
        </div>
      </div>

      <Button
        variant={dailyClaimAvailable ? 'accent' : 'secondary'}
        size="sm"
        disabled={!dailyClaimAvailable}
        isLoading={isClaiming}
        onClick={handleClaim}
        className="shrink-0 font-black"
        leftIcon={dailyClaimAvailable ? <Gift className="w-4 h-4" /> : <Check className="w-4 h-4" />}
      >
        {dailyClaimAvailable ? 'Claim ₹10' : 'Claimed'}
      </Button>
    </div>
  )
}
