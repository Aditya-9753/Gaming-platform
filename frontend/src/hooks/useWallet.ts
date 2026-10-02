import { useCallback } from 'react'
import { useWalletStore } from '../store/wallet.store'
import { walletApi } from '../services/wallet.api'
import { showToast } from '../components/common/Toast'

export function useWallet() {
  const {
    balance,
    isLoading,
    setBalance,
    setLoading,
  } = useWalletStore()

  const fetchBalance = useCallback(async () => {
    setLoading(true)
    try {
      const b = await walletApi.getBalance()
      setBalance(b)
    } catch {
      showToast({ title: 'Wallet unavailable', message: 'Could not load balance from the server.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }, [setBalance, setLoading])

  const claimDaily = useCallback(async () => {
    const res = await walletApi.claimDailyBonus()
    setBalance({
      ...res.newBalance,
      dailyClaimAvailable: false,
      lastClaimDate: new Date().toISOString(),
    })
    showToast({ title: '₹10 Free Bonus Claimed! 🎉', type: 'success' })
    return res.amountPaise
  }, [setBalance])

  return {
    balance,
    isLoadingBalance: isLoading,
    dailyClaimAvailable: balance.dailyClaimAvailable,
    fetchBalance,
    claimDaily,
  }
}
