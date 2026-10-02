import React, { useState } from 'react'
import { Send } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'

export const AdminNotifications: React.FC = () => {
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [type, setType] = useState('promo')
  const [isSending, setIsSending] = useState(false)

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSending(true)
    try {
      const notificationType = type === 'system' || type === 'warning' ? 'SYSTEM' : type === 'promo' ? 'INFO' : 'ACCOUNT'
      const { data } = await apiClient.post<{ recipients_count: number }>('/admin/notifications/broadcast', {
        title, message, notification_type: notificationType,
      })
      showToast({
        title: 'Broadcast Dispatched',
        message: `Server queued notifications for ${data.recipients_count} recipients.`,
        type: 'success',
      })
      setTitle('')
      setMessage('')
    } catch {
      showToast({ title: 'Broadcast failed', message: 'Your permission may be missing or the server rejected this message.', type: 'error' })
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Broadcast In-App Alerts</h1>
        <p className="text-xs text-slate-400">Push real-time pop-ups and notifications to connected players</p>
      </div>

      <form onSubmit={handleSend} className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4">
        <Input
          label="Notification Title"
          placeholder="e.g. Happy Hour: 50% Bonus on Deposits!"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Category</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-purple-500"
          >
            <option value="promo">Promotional / Bonus</option>
            <option value="system">System Announcement</option>
            <option value="warning">Maintenance Notice</option>
            <option value="info">General Info</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Broadcast Message</label>
          <textarea
            rows={4}
            required
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Details of the announcement..."
            className="w-full bg-dark-elevated border border-dark-border rounded-xl p-3 text-xs text-white focus:outline-none focus:border-purple-500 resize-none"
          />
        </div>

        <Button
          type="submit"
          variant="primary"
          className="w-full font-bold"
          isLoading={isSending}
          leftIcon={<Send className="w-4 h-4" />}
        >
          Send Broadcast Now
        </Button>
      </form>
    </div>
  )
}

export const Notifications = AdminNotifications
