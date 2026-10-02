export interface UserProfile {
  id: string
  username: string
  avatar?: string
  phone?: string
  email?: string
  vipLevel: number
  totalWageredPaise: number
  kycStatus: 'pending' | 'verified' | 'rejected' | 'none'
  status: 'active' | 'suspended' | 'self_excluded'
  limits: ResponsiblePlayLimits
  createdAt: string
}

export interface ResponsiblePlayLimits {
  dailyBetLimitPaise?: number
  dailyLossLimitPaise?: number
  sessionTimeLimitMinutes?: number
  selfExcludedUntil?: string | null
}
