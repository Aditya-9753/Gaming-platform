import React, { useEffect, useMemo } from 'react'
import { create } from 'zustand'
import markUrl from '../../assets/brand/rudrawin-mark.webp'
// Solid-shape mask (no soft glow) so the shine never lights up the glow's box
import maskUrl from '../../assets/brand/rudrawin-mark-mask.webp'
import wordUrl from '../../assets/brand/rudrawin-wordmark.webp'
import './logo-splash.css'

const DURATION_MS = 2500
const REDUCED_MS = 1400

/** Set right after a successful sign-in; the splash clears it when it finishes. */
export const useLogoSplash = create<{ visible: boolean; show: () => void; hide: () => void }>((set) => ({
  visible: false,
  show: () => set({ visible: true }),
  hide: () => set({ visible: false }),
}))

/** Full-screen RudraWin logo intro. Mount once near the router root. */
export const LogoSplash: React.FC = () => {
  const { visible, hide } = useLogoSplash()

  useEffect(() => {
    if (!visible) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const timer = window.setTimeout(hide, reduced ? REDUCED_MS : DURATION_MS)
    return () => window.clearTimeout(timer)
  }, [visible, hide])

  // Sparks fly out from behind the mark in random directions
  const sparks = useMemo(() => Array.from({ length: 18 }, (_, i) => {
    const angle = (i / 18) * Math.PI * 2 + Math.random() * 0.4
    const dist = 140 + Math.random() * 160
    return {
      '--dx': `${Math.cos(angle) * dist}px`,
      '--dy': `${Math.sin(angle) * dist}px`,
      animationDelay: `${0.5 + Math.random() * 0.5}s`,
    } as React.CSSProperties
  }), [visible]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!visible) return null
  const maskStyle = { maskImage: `url(${maskUrl})`, WebkitMaskImage: `url(${maskUrl})` } as React.CSSProperties
  return (
    <div className="rw-splash" role="presentation" onClick={hide}>
      <div className="rw-splash__rays" />
      <div className="rw-splash__stage">
        {sparks.map((style, i) => <span key={i} className="rw-splash__spark" style={style} />)}
        <div className="rw-splash__mark-wrap">
          <img src={markUrl} alt="" className="rw-splash__mark" draggable={false} />
          <div className="rw-splash__shine" style={maskStyle} />
        </div>
        <img src={wordUrl} alt="RudraWin" className="rw-splash__word" draggable={false} />
        <div className="rw-splash__beam" />
      </div>
    </div>
  )
}
