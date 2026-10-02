import { create } from 'zustand'

type Theme = 'dark' | 'light'
type Locale = 'en' | 'hi'

interface UIState {
  theme: Theme
  locale: Locale
  soundEnabled: boolean
  ageGateCleared: boolean
  sidebarOpen: boolean

  setTheme: (t: Theme) => void
  setLocale: (l: Locale) => void
  toggleSound: () => void
  clearAgeGate: () => void
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
}

export const useUIStore = create<UIState>((set) => ({
  theme: 'dark',
  locale: (localStorage.getItem('locale') as Locale) || 'en',
  soundEnabled: localStorage.getItem('sound') !== 'false',
  ageGateCleared: localStorage.getItem('ageGate') === 'true',
  sidebarOpen: false,

  setTheme: (t) => set({ theme: t }),
  setLocale: (l) => {
    localStorage.setItem('locale', l)
    set({ locale: l })
  },
  toggleSound: () =>
    set((s) => {
      const next = !s.soundEnabled
      localStorage.setItem('sound', String(next))
      return { soundEnabled: next }
    }),
  clearAgeGate: () => {
    localStorage.setItem('ageGate', 'true')
    set({ ageGateCleared: true })
  },
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}))

