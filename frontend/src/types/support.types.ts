export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent'
export type TicketStatus = 'open' | 'in_progress' | 'resolved' | 'closed'

export interface SupportTicketMessage {
  id: string
  senderId: string
  senderRole: 'user' | 'agent'
  message: string
  createdAt: string
}

export interface SupportTicket {
  id: string
  userId: string
  subject: string
  category: 'deposit' | 'withdrawal' | 'gameplay' | 'account' | 'fairness' | 'other'
  priority: TicketPriority
  status: TicketStatus
  messages: SupportTicketMessage[]
  createdAt: string
  updatedAt: string
}
