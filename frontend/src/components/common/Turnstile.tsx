import React, { useEffect, useRef } from 'react'
import axios from 'axios'

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: { sitekey: string; callback: (token: string) => void; 'expired-callback'?: () => void; theme?: string }) => string
      remove: (id: string) => void
    }
  }
}

const SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
let loading: Promise<void> | null = null

const loadScript = () => {
  if (window.turnstile) return Promise.resolve()
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const tag = document.createElement('script')
      tag.src = SCRIPT
      tag.async = true
      tag.onload = () => resolve()
      tag.onerror = () => { loading = null; reject(new Error('captcha script failed to load')) }
      document.head.appendChild(tag)
    })
  }
  return loading
}

/** Cloudflare Turnstile captcha; the server asks for it after repeated failed sign-ins. */
export const Turnstile: React.FC<{ siteKey: string; onToken: (token: string | null) => void }> = ({ siteKey, onToken }) => {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let id: string | null = null
    let cancelled = false
    loadScript().then(() => {
      if (cancelled || !box.current || !window.turnstile) return
      id = window.turnstile.render(box.current, { sitekey: siteKey, theme: 'dark', callback: onToken, 'expired-callback': () => onToken(null) })
    }).catch(() => onToken(null))
    return () => {
      cancelled = true
      if (id && window.turnstile) window.turnstile.remove(id)
    }
  }, [siteKey, onToken])
  return <div ref={box} className="flex min-h-[65px] justify-center" />
}

/** Site key from a CAPTCHA_REQUIRED sign-in error, else null. */
export const captchaSiteKey = (error: unknown): string | null => {
  if (!axios.isAxiosError(error)) return null
  const body = error.response?.data as { error?: { code?: string; details?: { site_key?: string } } } | undefined
  return body?.error?.code === 'CAPTCHA_REQUIRED' ? body.error.details?.site_key || null : null
}
