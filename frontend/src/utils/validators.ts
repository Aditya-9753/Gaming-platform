/**
 * Validate standard 10-digit Indian mobile number
 */
export function isValidPhone(phone: string): boolean {
  const cleaned = phone.replace(/[\s-+()]/g, '')
  // Accepts 10-digit numbers optionally prefixed with 91 or 0
  return /^(?:(?:\+|0{0,2})91(\s*[-]\s*)?|[0]?)?[6789]\d{9}$/.test(cleaned)
}

/**
 * Validate email address format
 */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

/**
 * Validate bet amount limits
 */
export function validateBetAmount(
  amountPaise: number,
  balancePaise: number,
  minPaise = 1000,
  maxPaise = 10000000
): { valid: boolean; error?: string } {
  if (isNaN(amountPaise) || amountPaise <= 0) {
    return { valid: false, error: 'Please enter a valid bet amount' }
  }
  if (amountPaise < minPaise) {
    return { valid: false, error: `Minimum bet is ₹${minPaise / 100}` }
  }
  if (amountPaise > maxPaise) {
    return { valid: false, error: `Maximum bet is ₹${maxPaise / 100}` }
  }
  if (amountPaise > balancePaise) {
    return { valid: false, error: 'Insufficient wallet balance' }
  }
  return { valid: true }
}

/**
 * Password strength validator (minimum 8 chars, at least one number and letter)
 */
export function isStrongPassword(password: string): boolean {
  return password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password)
}
