import { create } from 'zustand'

/** Set right after a successful sign-in; the splash clears it when it finishes. */
export const useLogoSplash = create<{ visible: boolean; show: () => void; hide: () => void }>((set) => ({
  visible: false,
  show: () => set({ visible: true }),
  hide: () => set({ visible: false }),
}))
