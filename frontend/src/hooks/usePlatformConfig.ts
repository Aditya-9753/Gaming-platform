import { useEffect } from 'react'
import { create } from 'zustand'
import { apiClient } from '../services/api'

export interface PlatformConfig {
  platform_name: string
  platform_logo_url: string
  maintenance_mode: boolean
  maintenance_message: string
  daily_claim_amount_paise: number
}

interface ConfigState {
  config: PlatformConfig
  loaded: boolean
  set: (config: PlatformConfig) => void
}

const DEFAULTS: PlatformConfig = {
  platform_name: 'Rudra247',
  platform_logo_url: '',
  maintenance_mode: false,
  maintenance_message: '',
  daily_claim_amount_paise: 1000,
}

export const usePlatformConfigStore = create<ConfigState>((set) => ({
  config: DEFAULTS,
  loaded: false,
  set: (config) => {
    const merged = { ...DEFAULTS, ...config }
    if (typeof document !== 'undefined' && merged.platform_name) document.title = `${merged.platform_name} — Live Games`
    set({ config: merged, loaded: true })
  },
}))

let inflight: Promise<void> | null = null

/** Re-fetch (e.g. right after the super admin saves settings). */
export function refreshPlatformConfig(): Promise<void> {
  inflight = apiClient.get<PlatformConfig>('/system/config')
    .then(({ data }) => usePlatformConfigStore.getState().set(data))
    .catch(() => undefined)
    .finally(() => { inflight = null })
  return inflight
}

/** Branding + maintenance flag set by the super admin (polled every minute). */
export function usePlatformConfig(): PlatformConfig {
  const config = usePlatformConfigStore((s) => s.config)
  useEffect(() => {
    if (!usePlatformConfigStore.getState().loaded && !inflight) void refreshPlatformConfig()
    const timer = setInterval(() => void refreshPlatformConfig(), 60000)
    return () => clearInterval(timer)
  }, [])
  return config
}
