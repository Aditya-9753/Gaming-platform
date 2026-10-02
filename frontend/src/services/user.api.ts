import { apiClient } from './api'
import type { UserProfile } from '../types/user.types'

export const userApi = {
  getProfile: async (): Promise<UserProfile> => {
    const { data } = await apiClient.get<Record<string, unknown>>('/users/me')
    return {
      id: String(data.id),
      username: String(data.username),
      email: String(data.email),
      vipLevel: 0,
      totalWageredPaise: 0,
      kycStatus: 'none',
      status: data.is_self_excluded ? 'self_excluded' : data.is_active ? 'active' : 'suspended',
      limits: {},
      createdAt: String(data.created_at),
    }
  },

  updateProfile: async (payload: Partial<UserProfile>): Promise<UserProfile> => {
    const { data } = await apiClient.put<Record<string, unknown>>('/users/me', {
      username: payload.username,
      email: payload.email,
    })
    return { ...payload, id: String(data.id), username: String(data.username), email: String(data.email) } as UserProfile
  },

  uploadAvatar: async (file: File): Promise<{ avatarUrl: string }> => {
    const form = new FormData()
    form.append('avatar', file)
    void form
    void file
    throw new Error('Avatar uploads are not supported by the backend')
  },
}
