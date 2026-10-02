export interface WalletBalance {
  realBalancePaise: number
  bonusBalancePaise: number
  totalBalancePaise: number
  currency: string
  dailyClaimAvailable: boolean
  lastClaimDate?: string
}

export type TransactionType = 'deposit' | 'withdrawal' | 'bet' | 'win' | 'bonus' | 'admin_adjustment' | 'refund'
export type TransactionStatus = 'pending' | 'completed' | 'failed' | 'rejected'

export interface WalletTransaction {
  id: string
  userId: string
  type: TransactionType
  amountPaise: number
  balanceAfterPaise: number
  status: TransactionStatus
  referenceId?: string
  description?: string
  createdAt: string
}

export interface DepositRequest {
  amountPaise: number
  paymentMethod: 'upi' | 'card' | 'crypto' | 'netbanking'
  idempotencyKey: string
}

export interface WithdrawalRequest {
  amountPaise: number
  upiId?: string
  bankAccount?: {
    accountNumber: string
    ifsc: string
    holderName: string
  }
  idempotencyKey: string
}
