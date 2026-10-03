import React from 'react'
import { MinesCell } from './MinesCell'

export interface CellState {
  revealed: boolean
  isMine: boolean
  isHit?: boolean
  ghost?: boolean
}

export interface MinesBoardProps {
  grid: CellState[]
  onCellClick: (index: number) => void
  disabled?: boolean
}

export const MinesBoard: React.FC<MinesBoardProps> = ({ grid, onCellClick, disabled = false }) => (
  <div className="mx-auto w-full max-w-[520px] grid grid-cols-5 gap-1.5 sm:gap-2.5 rounded-2xl sm:rounded-3xl bg-black/30 p-2 sm:p-4 touch-manipulation shadow-[inset_0_0_30px_rgba(0,0,0,0.5)] backdrop-blur-sm">
    {grid.map((cell, idx) => (
      <MinesCell
        key={idx}
        revealed={cell.revealed}
        isMine={cell.isMine}
        isHit={cell.isHit}
        ghost={cell.ghost}
        onClick={() => onCellClick(idx)}
        disabled={disabled}
      />
    ))}
  </div>
)
