import { PAISE_PER_RUPEE } from './constants'

/**
 * Format paise into Indian Rupee currency format (e.g. ₹1,250.00)
 */
export function formatPaiseToRupee(paise: number, showDecimal = true): string {
  const rupees = (paise || 0) / PAISE_PER_RUPEE
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: showDecimal ? 2 : 0,
    maximumFractionDigits: showDecimal ? 2 : 0,
  }).format(rupees)
}

/**
 * Convert user input Rupee amount to integer paise
 */
export function rupeeToPaise(rupees: number | string): number {
  const num = typeof rupees === 'string' ? parseFloat(rupees) : rupees
  if (isNaN(num) || num < 0) return 0
  return Math.round(num * PAISE_PER_RUPEE)
}

/**
 * Format Aviator / crash multiplier (e.g. 1.25x)
 */
export function formatMultiplier(multiplier: number): string {
  if (multiplier === undefined || multiplier === null || isNaN(multiplier)) return '1.00x'
  return `${multiplier.toFixed(2)}x`
}

/**
 * Format ISO date string or timestamp into readable date time
 */
export function formatDateTime(dateInput: string | number | Date): string {
  if (!dateInput) return '-'
  const date = new Date(dateInput)
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(date)
}

/**
 * Format seconds into mm:ss
 */
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

/**
 * Shorten wallet address or transaction ID
 */
export function truncateHash(hash: string, startChars = 6, endChars = 4): string {
  if (!hash || hash.length <= startChars + endChars) return hash
  return `${hash.slice(0, startChars)}...${hash.slice(-endChars)}`
}
