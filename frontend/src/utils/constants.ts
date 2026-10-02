export const APP_NAME = import.meta.env.VITE_APP_NAME || 'CasinoPulse'
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

export const PAISE_PER_RUPEE = 100

export const QUICK_BET_AMOUNTS = [10, 50, 100, 500, 1000, 5000] // In Rupees

export const COLORS = {
  red: '#EF4444',
  green: '#10B981',
  violet: '#8B5CF6',
}

export const STORAGE_KEYS = {
  THEME: 'cg_theme',
  LOCALE: 'cg_locale',
  SOUND_ENABLED: 'cg_sound_enabled',
  AGE_VERIFIED: 'cg_age_verified',
  SESSION_START: 'cg_session_start',
}
