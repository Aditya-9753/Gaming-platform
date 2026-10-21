export interface PasswordCheck { label: string; ok: boolean }

/** Same rules the backend enforces for staff passwords. */
export function checkPassword(password: string): { checks: PasswordCheck[]; score: number; valid: boolean } {
  const checks: PasswordCheck[] = [
    { label: '12+ characters', ok: password.length >= 12 },
    { label: 'Uppercase letter', ok: /[A-Z]/.test(password) },
    { label: 'Lowercase letter', ok: /[a-z]/.test(password) },
    { label: 'Number', ok: /\d/.test(password) },
    { label: 'Symbol (@$!%*?&_-#^)', ok: /[@$!%*?&_\-#^]/.test(password) },
  ]
  const passed = checks.filter((c) => c.ok).length
  const bonus = password.length >= 16 ? 1 : 0
  return { checks, score: Math.min(5, passed + bonus - (passed < 5 ? 1 : 0)), valid: passed === checks.length }
}
