import React from 'react'
import { numberColours } from './wingoRules'

const RING: Record<string, string> = {
  GREEN: '#10b981',
  RED: '#f43f5e',
  VIOLET: '#8b5cf6',
}

export interface WinGoBallProps {
  number: number
  size?: number
  onClick?: () => void
  disabled?: boolean
  selected?: boolean
}

/** Glossy lottery ball; 0 and 5 are split with violet like the classic game. */
export const WinGoBall: React.FC<WinGoBallProps> = ({ number, size = 56, onClick, disabled, selected }) => {
  const colours = numberColours(number)
  const ring = colours.length === 2
    ? `conic-gradient(from 200deg, ${RING[colours[0]]} 0 50%, ${RING.VIOLET} 50% 100%)`
    : RING[colours[0]]
  const textColour = colours.includes('VIOLET') ? (colours[0] === 'RED' ? '#e11d48' : '#059669') : RING[colours[0]]
  const content = (
    <span
      className="relative inline-flex items-center justify-center rounded-full shadow-[inset_0_-4px_8px_rgba(0,0,0,0.25),0_4px_10px_rgba(0,0,0,0.25)]"
      style={{ width: size, height: size, background: ring }}
    >
      <span
        className="absolute rounded-full bg-white flex items-center justify-center"
        style={{ inset: size * 0.14, boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.18)' }}
      >
        <span className="font-black" style={{ fontSize: size * 0.42, color: textColour, lineHeight: 1 }}>{number}</span>
      </span>
      <span className="absolute rounded-full bg-white/50" style={{ width: size * 0.22, height: size * 0.12, top: size * 0.08, left: size * 0.22, filter: 'blur(1px)' }} />
    </span>
  )
  if (!onClick) return content
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={`Number ${number}`}
      className={`rounded-full transition active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed ${selected ? 'ring-4 ring-amber-400/80' : ''}`}
    >
      {content}
    </button>
  )
}
