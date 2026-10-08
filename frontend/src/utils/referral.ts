import { partnerApi } from '../services/affiliate.api'

/**
 * Partner attribution on the main site (first-party, this domain only).
 *
 * - `/?ref=CODE&sub1=…` (query-style partner link): the click is logged through the API and its click_id kept.
 * - `?click_id=…` (arrival from the /r/CODE redirect): the click_id is kept as is.
 * - `?promo=CODE`: prefilled into the sign-up form.
 * The values live for the cookie lifetime the server reports (default 30 days) and are sent with sign-up.
 */
const KEY = 'aff_ref'

interface Stored {
  click_id?: string
  promo?: string
  expires: number
}

const read = (): Stored | null => {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as Stored
    if (!data.expires || data.expires < Date.now()) {
      localStorage.removeItem(KEY)
      return null
    }
    return data
  } catch {
    return null
  }
}

const write = (patch: Partial<Stored>, days: number) => {
  try {
    const current = read()
    // last click wins: a new click replaces the previous one
    localStorage.setItem(KEY, JSON.stringify({ ...current, ...patch, expires: Date.now() + days * 86_400_000 }))
  } catch {
    /* storage blocked: attribution falls back to the server cookie */
  }
}

let started = false

export async function captureReferral(): Promise<void> {
  if (started || typeof window === 'undefined' || window.location.pathname.startsWith('/partner') || window.location.pathname.startsWith('/admin')) return
  started = true
  const url = new URL(window.location.href)
  const ref = url.searchParams.get('ref')
  const clickId = url.searchParams.get('click_id')
  const promo = url.searchParams.get('promo')
  if (!ref && !clickId && !promo) return
  if (clickId && /^[0-9A-Za-z]{26}$/.test(clickId)) write({ click_id: clickId.toUpperCase() }, 30)
  if (promo) write({ promo: promo.slice(0, 32).toUpperCase() }, 30)
  if (ref && /^[0-9A-Za-z]{1,24}$/.test(ref) && !clickId) {
    try {
      const subs = Object.fromEntries(['sub1', 'sub2', 'sub3', 'sub4', 'sub5'].map((k) => [k, url.searchParams.get(k) || undefined]))
      const res = await partnerApi.trackClick({ ref, ...subs, referrer: document.referrer || undefined })
      if (res.tracked && res.click_id) write({ click_id: res.click_id }, res.cookie_days || 30)
    } catch {
      /* tracking must never break the page */
    }
  }
  for (const k of ['ref', 'click_id', 'promo', 'sub1', 'sub2', 'sub3', 'sub4', 'sub5']) url.searchParams.delete(k)
  window.history.replaceState(window.history.state, '', url.pathname + (url.search ? url.search : '') + url.hash)
}

export const getReferral = (): { click_id?: string; promo?: string } => {
  const data = read()
  return data ? { click_id: data.click_id, promo: data.promo } : {}
}

export const clearReferral = () => {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
