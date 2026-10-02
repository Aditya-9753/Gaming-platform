import { apiClient } from './api'
import type { WalletTransaction } from '../types/wallet.types'

export const transactionApi = {
  getTransactions: async (
    page = 1,
    limit = 20,
    type?: string
  ): Promise<{ items: WalletTransaction[]; total: number; page: number }> => {
    const { data } = await apiClient.get('/transactions', { params: { page, limit, type } })
    return data
  },
}

