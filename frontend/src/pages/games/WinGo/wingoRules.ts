/** Client mirror of backend app/games/wingo/rules.py (display + win preview only). */

export type WingoColour = 'GREEN' | 'RED' | 'VIOLET'
export type WingoSize = 'BIG' | 'SMALL'
export type WingoBetType = 'COLOR' | 'NUMBER' | 'SIZE'

export interface WingoMode { gameId: string; label: string; short: string; duration: number }

export const WINGO_MODES: WingoMode[] = [
  { gameId: 'wingo_30s', label: 'WinGo 30sec', short: '30sec', duration: 30 },
  { gameId: 'wingo_1m', label: 'WinGo 1 Min', short: '1 Min', duration: 60 },
  { gameId: 'wingo_3m', label: 'WinGo 3 Min', short: '3 Min', duration: 180 },
  { gameId: 'wingo_5m', label: 'WinGo 5 Min', short: '5 Min', duration: 300 },
]

export const numberColours = (n: number): WingoColour[] =>
  n === 0 ? ['RED', 'VIOLET'] : n === 5 ? ['GREEN', 'VIOLET'] : n % 2 ? ['GREEN'] : ['RED']

export const numberSize = (n: number): WingoSize => (n >= 5 ? 'BIG' : 'SMALL')

export const DEFAULT_PAYOUTS_X100: Record<string, number> = {
  GREEN: 200, RED: 200, COLOR_HALF: 150, VIOLET: 450, NUMBER: 900, SIZE: 196,
}

export interface WingoPick { type: WingoBetType; value: string }

export function payoutX100(pick: WingoPick, number: number, payouts: Record<string, number> = DEFAULT_PAYOUTS_X100): number {
  if (pick.type === 'NUMBER') return Number(pick.value) === number ? payouts.NUMBER : 0
  if (pick.type === 'SIZE') return pick.value === numberSize(number) ? payouts.SIZE : 0
  const colours = numberColours(number)
  if (pick.value === 'VIOLET') return colours.includes('VIOLET') ? payouts.VIOLET : 0
  if (!colours.includes(pick.value as WingoColour)) return 0
  return colours.includes('VIOLET') ? payouts.COLOR_HALF : payouts[pick.value]
}

export const pickLabel = (pick: WingoPick) =>
  pick.type === 'NUMBER' ? pick.value : pick.value.charAt(0) + pick.value.slice(1).toLowerCase()

/** Theme colour for a pick (sheet header, buttons). */
export const pickTheme = (pick: WingoPick): string => {
  if (pick.type === 'SIZE') return pick.value === 'BIG' ? 'from-amber-400 to-orange-500' : 'from-sky-400 to-blue-500'
  if (pick.type === 'NUMBER') {
    const c = numberColours(Number(pick.value))
    return c.includes('VIOLET') ? (c[0] === 'RED' ? 'from-rose-500 to-violet-500' : 'from-emerald-500 to-violet-500') : c[0] === 'RED' ? 'from-rose-500 to-rose-600' : 'from-emerald-500 to-emerald-600'
  }
  return pick.value === 'GREEN' ? 'from-emerald-500 to-emerald-600' : pick.value === 'RED' ? 'from-rose-500 to-rose-600' : 'from-violet-500 to-violet-600'
}
