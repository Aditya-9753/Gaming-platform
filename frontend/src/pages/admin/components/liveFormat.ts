import { formatPaiseToRupee } from '../../../utils/formatters'

export const GAME_LABEL: Record<string, string> = {
  teen_patti: 'Teen Patti',
  aviator: 'Aviator', mines: 'Mines', cricket: 'Cricket', color: 'Color (old)',
  wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m',
}

export interface BetRow {
  id: string; user_id: string; username: string; game_id: string; round_id: string; round_no: number | null
  amount: number; pick: string; status: string; payout: number; multiplier: number | null; revealed?: number | null; at: string
}

export const ago = (iso: string | null | undefined, now: number) => {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export const countdown = (iso: string | undefined, now: number) => {
  if (!iso) return null
  const s = Math.max(0, Math.ceil((Date.parse(iso) - now) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const money = (paise: number) => formatPaiseToRupee(paise)
export const signed = (paise: number) => `${paise >= 0 ? '+' : '−'}${formatPaiseToRupee(Math.abs(paise))}`
export const statusTone: Record<string, string> = { WON: 'text-emerald-400', LOST: 'text-rose-400', PLACED: 'text-amber-300', REFUNDED: 'text-slate-300', CANCELLED: 'text-slate-400' }

export const betResult = (b: Pick<BetRow, 'status' | 'payout' | 'multiplier'>) =>
  b.status === 'WON' ? `+${money(b.payout)}${b.multiplier ? ` (${b.multiplier.toFixed(2)}x)` : ''}` : b.status === 'PLACED' ? 'In play' : b.status
