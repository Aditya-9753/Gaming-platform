import React from 'react'
import { GoldGem, SkullBomb } from './MinesArt'

export interface MinesCellProps {
  revealed: boolean
  isMine: boolean
  /** The mine the player actually stepped on. */
  isHit?: boolean
  /** Revealed only because the round ended (not picked by the player). */
  ghost?: boolean
  onClick: () => void
  disabled?: boolean
}

export const MinesCell: React.FC<MinesCellProps> = ({
  revealed,
  isMine,
  isHit = false,
  ghost = false,
  onClick,
  disabled = false,
}) => {
  const base = 'relative w-full aspect-square rounded-2xl flex items-center justify-center transition-all duration-200 select-none'
  if (!revealed) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        aria-label="Hidden tile"
        className={`${base} bg-gradient-to-b from-[#5b2a86] to-[#3a1760] border-b-4 border-[#26103f] shadow-[inset_0_2px_0_rgba(255,255,255,0.15)] hover:from-[#6d34a0] hover:-translate-y-0.5 active:translate-y-0.5 active:border-b-2 disabled:cursor-not-allowed disabled:hover:translate-y-0`}
      >
        <span className="h-3 w-3 rounded-full bg-white/10" />
      </button>
    )
  }
  return (
    <div
      className={`${base} ${
        isMine
          ? isHit
            ? 'bg-gradient-to-b from-rose-500 to-red-700 shadow-[0_0_25px_rgba(244,63,94,0.8)] animate-[pulse_0.6s_ease-in-out_2]'
            : 'bg-[#2a1240]'
          : 'bg-gradient-to-b from-amber-200/30 to-amber-500/20 border border-amber-300/60 shadow-[0_0_18px_rgba(251,191,36,0.35)]'
      } ${ghost ? 'opacity-50' : ''}`}
    >
      {isMine ? <SkullBomb className="w-[78%] h-[78%]" lit={isHit} /> : <GoldGem className="w-[70%] h-[70%] drop-shadow-[0_2px_6px_rgba(251,191,36,0.7)]" />}
    </div>
  )
}
