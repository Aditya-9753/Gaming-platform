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
  loadedAt: number
  load: () => Promise<PartnerMe | null>
  /** Re-fetch only when the data is older than `maxAgeMs` (page changes, tab focus). */
  refresh: (maxAgeMs?: number) => void
  setLocale: (locale: string) => void
  clear: () => void
}

export const usePartnerStore = create<PartnerState>((set, get) => ({
  me: null,
  error: null,
  locale: readLocale(),
  loadedAt: 0,
  load: async () => {
    try {
      const me = await partnerApi.me()
      set({ me, error: null, loadedAt: Date.now() })
      return me
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'failed' })
      return null
    }
  },
  refresh: (maxAgeMs = 30_000) => {
    if (!get().me || Date.now() - get().loadedAt > maxAgeMs) void get().load()
  },
  setLocale: (locale) => {
    if (locale === 'en' || locale === 'hi') useUIStore.getState().setLocale(locale)
    set({ locale })
  },
  clear: () => set({ me: null, error: null, loadedAt: 0 }),
}))
