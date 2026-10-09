import { useCallback } from 'react'
import { useUIStore } from '../store/ui.store'
import hi from './locales/hi.json'

/**
 * Site translations. The English text itself is the key: `t('Wallet')`.
 * A language dictionary maps English -> translation; anything missing falls back to English,
 * so the page is never blank. Placeholders: `t('Won {amount}', { amount })`.
 */
export type Locale = 'en' | 'hi'

const DICTIONARIES: Record<string, Record<string, string>> = { hi }

export function translate(locale: string, text: string, vars?: Record<string, string | number>): string {
  const out = (locale !== 'en' && DICTIONARIES[locale]?.[text]) || text
  if (!vars) return out
  return out.replace(/\{(\w+)\}/g, (match, key: string) => (key in vars ? String(vars[key]) : match))
}

export type TFunction = (text: string, vars?: Record<string, string | number>) => string

/** Hook: re-renders the component when the language changes. */
export function useT(): TFunction {
  const locale = useUIStore((s) => s.locale)
  return useCallback((text: string, vars?: Record<string, string | number>) => translate(locale, text, vars), [locale])
}

/** For code outside components (toasts, helpers): uses the current language. */
export const t: TFunction = (text, vars) => translate(useUIStore.getState().locale, text, vars)
