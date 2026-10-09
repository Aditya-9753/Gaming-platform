import { create } from 'zustand'
import { partnerApi } from '../../services/affiliate.api'
import { useUIStore } from '../../store/ui.store'
import type { PartnerMe } from '../../types/affiliate.types'

// One language setting for the whole site: the partner portal follows the main switch
const readLocale = () => useUIStore.getState().locale

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
    if (locale === 'en' || locale === 'hi') useUIStore.getState().setLocale(locale)
    set({ locale })
  },
  clear: () => set({ me: null, error: null }),
}))
