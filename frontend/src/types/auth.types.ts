/** 'staff' = a custom role created in the Roles system. */
export type UserRole = 'user' | 'support' | 'auditor' | 'admin' | 'superadmin' | 'staff'

/** Roles that can open the admin panel (backend still enforces per-permission access). */
export const STAFF_ROLES: UserRole[] = ['superadmin', 'admin', 'support', 'auditor', 'staff']

export const isStaffRole = (role?: UserRole | null): boolean =>
  Boolean(role && STAFF_ROLES.includes(role))

export interface UserSession {
  id: string
  username: string
  phone?: string
  email?: string
  role: UserRole
  /** Exact role name from the backend (e.g. GAME_OPERATOR for custom roles). */
  roleName?: string
  fullName?: string
  permissions: string[]
  isVerified: boolean
  has2FA: boolean
  /** True when the backend requires this admin to finish TOTP setup first. */
  requires2FASetup?: boolean
  createdAt: string
}

export interface AuthTokens {
  accessToken: string
  expiresIn: number
}

export interface LoginCredentials {
  username: string
  password: string
  totpCode?: string
}

export interface RegisterCredentials {
  username: string
  email?: string
  password: string
  ageConfirmed: boolean
}

export interface AuthResponse {
  user: UserSession
  accessToken: string
}
