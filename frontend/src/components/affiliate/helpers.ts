import React, { useState } from 'react'
import { t as tr } from '../../i18n'
import { useAuthStore } from '../../store/auth.store'
import { getApiErrorMessage } from '../../utils/apiError'
import { showToast } from '../common/toastBus'

/** Formatting helpers, contexts and hooks shared by the partner portal and the affiliate back office. */

/**
 * True inside the partner portal: cards, buttons and tabs switch to the RunWin
 * premium look (glass, gradients, entrance motion; see components/brand/brand.css).
 * The affiliate back office leaves it off and keeps the plain admin style.
 */
export const PremiumUI = React.createContext(false)
export const usePremium = () => React.useContext(PremiumUI)

export const cx = (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(' ')

export const usd = (value: string | number | null | undefined, sign = false): string => {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return '—'
  const text = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${n < 0 ? '-' : sign && n > 0 ? '+' : ''}${text} $`
}

/**
 * Affiliate amounts are kept in USD. The partner portal can show them in rupees: `perUsd` is
 * the latest ECB rate (₹ per $). The back office keeps USD (the default).
 */
export interface DisplayCurrency { code: 'USD' | 'INR'; perUsd: number }
export const DisplayCurrencyContext = React.createContext<DisplayCurrency>({ code: 'USD', perUsd: 1 })

export const formatMoney = (value: string | number | null | undefined, currency: DisplayCurrency, sign = false): string => {
  if (currency.code === 'USD') return usd(value, sign)
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value) * currency.perUsd
  if (!Number.isFinite(n)) return '—'
  const text = Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${n < 0 ? '-' : sign && n > 0 ? '+' : ''}₹${text}`
}

/** Formats an affiliate (USD) amount in the currency the viewer chose. */
export const useMoney = () => {
  const currency = React.useContext(DisplayCurrencyContext)
  return React.useCallback((value: string | number | null | undefined, sign = false) => formatMoney(value, currency, sign), [currency])
}

export const pct = (rate: string | number | null | undefined) =>
  rate === null || rate === undefined ? '—' : `${(Number(rate) * 100).toFixed(Number(rate) * 100 % 1 ? 2 : 0)}%`

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export const dateOnly = (iso: string | null | undefined) =>
  iso ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

export const errorText = (e: unknown, fallback?: string) => getApiErrorMessage(e, fallback ?? tr('Something went wrong'))

export const toastError = (e: unknown, title?: string) =>
  showToast({ title: title ?? tr('Could not complete'), message: errorText(e), type: 'error', duration: 6000 })

// Last result of each partner-portal loader, so a page opened again shows its data at once
// and refreshes it in the background (cleared on sign-out; keyed by the signed-in user).
const asyncCache = new Map<string, unknown>()
export const clearAsyncCache = () => asyncCache.clear()

export function useAsync<T>(loader: () => Promise<T>, deps: React.DependencyList = []) {
  const premium = usePremium()
  const userId = useAuthStore((s) => s.user?.id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const key = React.useMemo(() => (premium ? `${userId}|${loader.toString()}|${JSON.stringify(deps)}` : null), [premium, userId, ...deps])
  const [data, setData] = useState<T | null>(() => (key && asyncCache.has(key) ? (asyncCache.get(key) as T) : null))
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const reload = React.useCallback(async () => {
    setLoading(true)
    try {
      const value = await loader()
      if (key) asyncCache.set(key, value)
      setData(value)
      setError(null)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ...deps])
  React.useEffect(() => { void reload() }, [reload])
  return { data, error, loading, reload, setData }
}
