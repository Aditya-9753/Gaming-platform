import { apiClient } from './api'
import { STAFF_ROLES, type UserRole, type UserSession } from '../types/auth.types'

export interface TokenResponse {
  access_token: string
  expires_in: number
}

interface ApiUser {
  id: string
  username: string
  email: string | null
  role: string
  is_active: boolean
  is_verified: boolean
  totp_enabled: boolean
  requires_2fa_setup?: boolean
  is_staff?: boolean
  full_name?: string | null
  permissions?: string[]
}

const mapUser = (user: ApiUser): UserSession => {
  const role = user.role.toLowerCase()
  return {
    id: user.id,
    username: user.username,
    email: user.email ?? undefined,
    role: role === 'partner' ? 'partner' : (STAFF_ROLES as string[]).includes(role) ? (role as UserRole) : user.is_staff ? 'staff' : 'user',
    roleName: user.role,
    fullName: user.full_name ?? undefined,
    permissions: user.permissions ?? [],
    isVerified: user.is_verified,
    has2FA: user.totp_enabled,
    requires2FASetup: Boolean(user.requires_2fa_setup),
    createdAt: new Date().toISOString(),
  }
}

export const authApi = {
  /** `username` may be the username or the email address. */
  login: async (username: string, password: string, totpCode?: string, captchaToken?: string | null) => {
    const { data } = await apiClient.post<TokenResponse>('/auth/login', {
      username: username.trim(),
      password,
      totp_code: totpCode || undefined,
      captcha_token: captchaToken || undefined,
    })
    return data
  },
  register: async (username: string, password: string, ageConfirmed: boolean, email?: string, referral?: { click_id?: string; promo_code?: string }) => {
    const { data } = await apiClient.post<TokenResponse>('/auth/register', {
      username: username.trim(),
      email: email?.trim() || undefined,
      password,
      age_confirmed: ageConfirmed,
      click_id: referral?.click_id || undefined,
      promo_code: referral?.promo_code?.trim() || undefined,
    })
    return data
  },
  refreshToken: async () => {
    const { data, status } = await apiClient.post<TokenResponse | undefined>('/auth/refresh')
    return status === 204 ? null : data ?? null
  },
  getCurrentUser: async (): Promise<UserSession> => {
    const { data } = await apiClient.get<ApiUser>('/auth/me')
    return mapUser(data)
  },
  logout: async () => {
    await apiClient.post('/auth/logout')
  },
  forgotPassword: async (email: string) => {
    await apiClient.post('/auth/forgot-password', { email })
  },
  resetPassword: async (token: string, newPassword: string) => {
    await apiClient.post('/auth/reset-password', { token, new_password: newPassword })
  },
}
