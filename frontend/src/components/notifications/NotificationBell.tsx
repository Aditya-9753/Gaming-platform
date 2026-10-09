import React, { useState, useRef, useEffect } from 'react'
import { Bell } from 'lucide-react'
import { useNotificationStore } from '../../store/notification.store'
import { NotificationItem } from './NotificationItem'
import { t as tr } from '../../i18n'

export const NotificationBell: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false)
  const { notifications, unreadCount, markRead, markAllRead } = useNotificationStore()
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 text-slate-400 hover:text-white rounded-xl hover:bg-dark-elevated transition-colors"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 w-4 h-4 bg-rose-500 text-white rounded-full text-[10px] font-black flex items-center justify-center animate-pulse">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-dark-card border border-dark-border rounded-2xl shadow-2xl p-4 z-50 animate-in fade-in">
          <div className="flex items-center justify-between pb-3 border-b border-dark-border mb-3">
            <h4 className="text-sm font-bold text-white">{tr('Notifications')}</h4>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-emerald-400 hover:underline font-semibold"
              >
                Mark all as read
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto space-y-2">
            {notifications.length === 0 ? (
              <div className="text-center py-6 text-xs text-slate-500">
                {tr('No notifications yet')}
              </div>
            ) : (
              notifications.map((n) => (
                <NotificationItem key={n.id} notification={n} onRead={markRead} />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

