import { apiClient } from './api'
import type { SupportTicket, SupportTicketMessage } from '../types/support.types'
import { useAuthStore } from '../store/auth.store'

interface ApiMessage {
  id: string
  sender_id?: string
  sender_name?: string
  message: string
  created_at: string
}
interface ApiTicket {
  id: string
  subject: string
  status: string
  priority: string
  assigned_to_id?: string | null
  created_at: string
  updated_at?: string
  messages?: ApiMessage[]
}

const mapMessage = (message: ApiMessage): SupportTicketMessage => ({
  id: message.id,
  senderId: message.sender_id || message.sender_name || 'support',
  senderRole: message.sender_id === useAuthStore.getState().user?.id ? 'user' : 'agent',
  message: message.message,
  createdAt: message.created_at,
})
const mapTicket = (ticket: ApiTicket): SupportTicket => ({
  id: ticket.id,
  userId: '',
  subject: ticket.subject,
  category: 'other',
  priority: ticket.priority.toLowerCase() as SupportTicket['priority'],
  status: ticket.status.toLowerCase() as SupportTicket['status'],
  messages: (ticket.messages || []).map(mapMessage),
  createdAt: ticket.created_at,
  updatedAt: ticket.updated_at || ticket.created_at,
})

export const supportApi = {
  getTickets: async (): Promise<SupportTicket[]> => {
    const { data } = await apiClient.get<{ items: ApiTicket[] }>('/support/tickets', { params: { page: 1, page_size: 50 } })
    return data.items.map(mapTicket)
  },
  getTicket: async (id: string): Promise<SupportTicket> => {
    const { data } = await apiClient.get<ApiTicket>(`/support/tickets/${id}`)
    return mapTicket(data)
  },
  createTicket: async (payload: { subject: string; category?: string; message: string }): Promise<SupportTicket> => {
    const { data } = await apiClient.post<ApiTicket>('/support/tickets', {
      subject: payload.subject,
      message: payload.message,
    })
    return mapTicket(data)
  },
  replyTicket: async (id: string, message: string): Promise<SupportTicketMessage> => {
    const { data } = await apiClient.post<ApiMessage>(`/support/tickets/${id}/reply`, { message })
    return mapMessage(data)
  },
}
