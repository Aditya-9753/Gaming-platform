import { create } from 'zustand'
import type { WalletBalance, WalletTransaction } from '../types/wallet.types'

interface WalletState {
  balance: WalletBalance
  transactions: WalletTransaction[]
  isLoading: boolean
  isClaimingDaily: boolean
  setBalance: (balance: Partial<WalletBalance>) => void
  setTransactions: (transactions: WalletTransaction[]) => void
  addTransaction: (tx: WalletTransaction) => void
  setLoading: (loading: boolean) => void
  setClaimingDaily: (claiming: boolean) => void
}

const initialBalance: WalletBalance = {
  realBalancePaise: 0,
  bonusBalancePaise: 0,
  totalBalancePaise: 0,
  currency: 'INR',
  dailyClaimAvailable: true,
}

export const useWalletStore = create<WalletState>((set) => ({
  balance: initialBalance,
  transactions: [],
  isLoading: false,
  isClaimingDaily: false,

  setBalance: (newBalance) =>
    set((state) => {
      const merged = { ...state.balance, ...newBalance }
      merged.totalBalancePaise = merged.realBalancePaise + merged.bonusBalancePaise
      return { balance: merged }
    }),

  setTransactions: (transactions) => set({ transactions }),

  addTransaction: (tx) =>
    set((state) => ({
      transactions: [tx, ...state.transactions],
    })),

  setLoading: (loading) => set({ isLoading: loading }),
  setClaimingDaily: (isClaimingDaily) => set({ isClaimingDaily }),
}))
