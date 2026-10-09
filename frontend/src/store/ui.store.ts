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

function readLocale(): Locale {
  let value: string | null = null
  try { value = localStorage.getItem('locale') } catch { /* private mode */ }
  const locale: Locale = value === 'hi' ? 'hi' : 'en'
  if (typeof document !== 'undefined') document.documentElement.lang = locale
  return locale
}

export const useUIStore = create<UIState>((set) => ({
  theme: 'dark',
  locale: readLocale(),
  soundEnabled: localStorage.getItem('sound') !== 'false',
  ageGateCleared: localStorage.getItem('ageGate') === 'true',
  sidebarOpen: false,

  setTheme: (t) => set({ theme: t }),
  setLocale: (l) => {
    try { localStorage.setItem('locale', l) } catch { /* private mode */ }
    if (typeof document !== 'undefined') document.documentElement.lang = l
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

