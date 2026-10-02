import { wsClient } from './websocket'
import { WS_EVENTS_V1 } from './events'
import { useNotificationStore } from '../store/notification.store'
import { useWalletStore } from '../store/wallet.store'
import type { AppNotification } from '../types/notification.types'

export const notificationsSocket = {
  subscribe: () => {
    const unsubNotification = wsClient.on(WS_EVENTS_V1.NOTIFICATION_NEW, (notif: AppNotification) => {
      useNotificationStore.getState().addNotification(notif)
    })

    const unsubWallet = wsClient.on(WS_EVENTS_V1.WALLET_BALANCE_UPDATED, (data: { realBalancePaise: number; bonusBalancePaise: number }) => {
      useWalletStore.getState().setBalance(data)
    })

    return () => {
      unsubNotification()
      unsubWallet()
    }
  },
}
