import { apiClient } from './api'
import type { WalletBalance, WalletTransaction } from '../types/wallet.types'
import { useWalletStore } from '../store/wallet.store'

interface ApiWallet { balance: number; available_balance: number; currency: string }
interface ApiPage<T> { items: T[]; total: number; page: number; page_size: number }

export const walletApi = {
  getBalance: async (): Promise<WalletBalance> => {
    const { data } = await apiClient.get<ApiWallet>('/wallet')
    return {
      realBalancePaise: data.available_balance,
      bonusBalancePaise: data.balance - data.available_balance,
      totalBalancePaise: data.balance,
      currency: data.currency,
      dailyClaimAvailable: true,
    }
  },

  claimDailyBonus: async () => {
    const { data } = await apiClient.post<{ new_balance: number; transaction: { amount: number } }>('/wallet/daily-claim', {}, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    })
    return { amountPaise: data.transaction.amount, newBalance: await walletApi.getBalance() }
  },

  getTransactions: async (page = 1, pageSize = 20): Promise<{ items: WalletTransaction[]; total: number }> => {
    const { data } = await apiClient.get<ApiPage<Record<string, unknown>> | Array<Record<string, unknown>>>('/wallet/transactions', { params: { page, page_size: pageSize } })
    const items = Array.isArray(data) ? data : data.items
    const total = Array.isArray(data) ? data.length : data.total
    return {
      items: items.map((row) => ({
        id: String(row.id),
        userId: String(row.wallet_id),
        type: String(row.type).toLowerCase() as WalletTransaction['type'],
        amountPaise: Number(row.amount),
        balanceAfterPaise: Number(row.balance_after),
        status: String(row.status).toLowerCase() as WalletTransaction['status'],
        referenceId: row.reference ? String(row.reference) : undefined,
        description: row.description ? String(row.description) : undefined,
        createdAt: String(row.created_at),
      })),
      total,
    }
  },
}

export async function syncWalletBalance() {
  const balance = await walletApi.getBalance()
  useWalletStore.getState().setBalance(balance)
}
