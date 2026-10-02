import { create } from 'zustand'
import type { UserProfile, ResponsiblePlayLimits } from '../types/user.types'

interface UserState {
  profile: UserProfile | null
  limits: ResponsiblePlayLimits | null
  isLoadingProfile: boolean

  setProfile: (p: UserProfile) => void
  setLimits: (l: Partial<ResponsiblePlayLimits>) => void
  setLoadingProfile: (v: boolean) => void
  clearUser: () => void
}

export const useUserStore = create<UserState>((set) => ({
  profile: null,
  limits: null,
  isLoadingProfile: false,

  setProfile: (p) => set({ profile: p }),
  setLimits: (l) =>
    set((s) => ({
      limits: s.limits ? { ...s.limits, ...l } : (l as ResponsiblePlayLimits),
    })),
  setLoadingProfile: (v) => set({ isLoadingProfile: v }),
  clearUser: () => set({ profile: null, limits: null }),
}))

