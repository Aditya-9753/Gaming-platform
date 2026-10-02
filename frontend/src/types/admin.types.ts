export interface AdminStats {
  totalUsers: number
  activeUsersOnline: number
  totalGGRPaise: number // Gross Gaming Revenue
  totalDepositsPaise: number
  totalWithdrawalsPaise: number
  activeGameRoundsCount: number
}

export interface AdminUserRecord {
  id: string
  username: string
  phone: string
  email: string
  role: UserRole
  balancePaise: number
  status: 'active' | 'suspended' | 'banned'
  kycStatus?: 'pending' | 'verified' | 'rejected' | 'none'
  createdAt: string
  lastLoginAt?: string
}

export interface WalletAdjustmentPayload {
  userId: string
  amountPaise: number // positive for credit, negative for debit
  reason: string
  adminId: string
  notes?: string
}

export interface GameSettingsPayload {
  gameId: string
  minBetPaise: number
  maxBetPaise: number
  houseEdgePercent: number
  bettingCountdownSeconds: number
  isActive: boolean
}

export interface AuditLogEntry {
  id: string
  adminId: string
  adminUsername: string
  action: string
  targetEntity: string
  targetId: string
  details: Record<string, unknown>
  ipAddress: string
  createdAt: string
}
import type { UserRole } from './auth.types'
