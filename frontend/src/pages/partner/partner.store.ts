import { create } from 'zustand'
import { partnerApi } from '../../services/affiliate.api'
import type { PartnerMe } from '../../types/affiliate.types'

const readLocale = () => {
  try {
    return localStorage.getItem('aff_locale') || 'en'
  } catch {
    return 'en'
  }
}

interface PartnerState {
  me: PartnerMe | null
  error: string | null
  locale: string
  load: () => Promise<PartnerMe | null>
  setLocale: (locale: string) => void
  clear: () => void
}

export const usePartnerStore = create<PartnerState>((set) => ({
  me: null,
  error: null,
  locale: readLocale(),
  load: async () => {
    try {
      const me = await partnerApi.me()
      set({ me, error: null })
      return me
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'failed' })
      return null
    }
  },
  setLocale: (locale) => {
    try {
      localStorage.setItem('aff_locale', locale)
    } catch {
      /* private mode */
    }
    set({ locale })
  },
  clear: () => set({ me: null, error: null }),
}))

/** Impersonation tokens live only in this tab (sessionStorage), never next to the admin's own session. */
export const IMPERSONATION_KEY = 'aff_impersonation_token'

export const readImpersonationToken = (): string | null => {
  try {
    return sessionStorage.getItem(IMPERSONATION_KEY)
  } catch {
    return null
  }
}
