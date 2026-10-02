import { apiClient } from './api'
import type { AppNotification } from '../types/notification.types'

export const notificationApi = {
  getNotifications: async (): Promise<AppNotification[]> => {
    const { data } = await apiClient.get<{ items: Array<Record<string, unknown>> }>('/notifications')
    return data.items.map((item) => ({
      id: String(item.id),
      title: String(item.title),
      message: String(item.message),
      type: String(item.type).toLowerCase() as AppNotification['type'],
      isRead: Boolean(item.is_read),
      createdAt: String(item.created_at),
    }))
  },

  markAsRead: async (id: string): Promise<void> => {
    await apiClient.post(`/notifications/${id}/read`)
  },

  markAllAsRead: async (): Promise<void> => {
    await apiClient.post('/notifications/read-all')
  },
}
