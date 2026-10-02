import { apiClient } from './api'
import type { AdminStats, AdminUserRecord, WalletAdjustmentPayload, GameSettingsPayload, AuditLogEntry } from '../types/admin.types'

export const adminApi = {
  getStats: async (): Promise<AdminStats> => {
    const { data } = await apiClient.get<AdminStats>('/admin/stats')
    return data
  },

  getUsers: async (page = 1, search?: string): Promise<{ items: AdminUserRecord[]; total: number }> => {
    const { data } = await apiClient.get('/admin/users', { params: { page, search } })
    return data
  },

  getUserDetails: async (id: string): Promise<AdminUserRecord> => {
    const { data } = await apiClient.get<AdminUserRecord>(`/admin/users/${id}`)
    return data
  },

  updateGameSettings: async (gameId: string, payload: GameSettingsPayload): Promise<void> => {
    await apiClient.patch(`/admin/games/${gameId}/settings`, payload)
  },

  manualWalletAdjustment: async (payload: WalletAdjustmentPayload): Promise<void> => {
    await apiClient.post('/admin/wallet/adjust', payload)
  },

  getAuditLogs: async (page = 1): Promise<{ items: AuditLogEntry[]; total: number }> => {
    const { data } = await apiClient.get('/admin/audit-logs', { params: { page } })
    return data
  },

  setup2FA: async (): Promise<{ otpauthUrl: string; secret: string }> => {
    const { data } = await apiClient.post<{ otpauthUrl: string; secret: string }>('/admin/2fa/setup')
    return data
  },

  verify2FA: async (token: string): Promise<void> => {
    await apiClient.post('/admin/2fa/verify', { token })
  },
}

