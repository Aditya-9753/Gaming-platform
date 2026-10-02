export type NotificationType = 'system' | 'wallet' | 'game' | 'promo' | 'security'

export interface AppNotification {
  id: string
  userId?: string
  title: string
  message: string
  type: NotificationType
  isRead: boolean
  actionUrl?: string
  createdAt: string
}
