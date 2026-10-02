import React from 'react'
import { Bell, Info, CheckCircle2, AlertTriangle, Shield } from 'lucide-react'
import type { AppNotification } from '../../types/notification.types'
import { formatDateTime } from '../../utils/formatters'

export interface NotificationItemProps {
  notification: AppNotification
  onRead?: (id: string) => void
}

export const NotificationItem: React.FC<NotificationItemProps> = ({
  notification,
  onRead,
}) => {
  const icons: Record<string, React.ReactNode> = {
    info: <Info className="w-4 h-4 text-cyan-400" />,
    success: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
    warning: <AlertTriangle className="w-4 h-4 text-amber-400" />,
    promo: <Bell className="w-4 h-4 text-purple-400" />,
    system: <Info className="w-4 h-4 text-slate-400" />,
    security: <Shield className="w-4 h-4 text-rose-400" />,
    wallet: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
    game: <Bell className="w-4 h-4 text-amber-400" />,
  }

  return (
    <div
      onClick={() => onRead?.(notification.id)}
      className={`p-3 rounded-xl border text-left cursor-pointer transition-colors ${
        notification.isRead
          ? 'bg-dark-card border-dark-border opacity-70'
          : 'bg-dark-elevated border-emerald-500/20'
      }`}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 shrink-0">{icons[notification.type] || <Info className="w-4 h-4 text-slate-400" />}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h5 className="text-xs font-bold text-white truncate">{notification.title}</h5>
            <span className="text-[10px] text-slate-500 shrink-0">
              {formatDateTime(notification.createdAt)}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{notification.message}</p>
        </div>
      </div>
    </div>
  )
}

