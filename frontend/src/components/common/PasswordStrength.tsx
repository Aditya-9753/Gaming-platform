import React from 'react'

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

const LEVELS = [
  { label: 'Too weak', bar: 'bg-rose-500', text: 'text-rose-400' },
  { label: 'Weak', bar: 'bg-rose-500', text: 'text-rose-400' },
  { label: 'Fair', bar: 'bg-amber-500', text: 'text-amber-400' },
  { label: 'Good', bar: 'bg-amber-400', text: 'text-amber-300' },
  { label: 'Strong', bar: 'bg-emerald-500', text: 'text-emerald-400' },
  { label: 'Very strong', bar: 'bg-emerald-400', text: 'text-emerald-300' },
]

export const PasswordStrength: React.FC<{ password: string }> = ({ password }) => {
  const { checks, score } = checkPassword(password)
  const level = LEVELS[Math.max(0, score)]
  return (
    <div className="space-y-2" aria-live="polite">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={`h-1.5 flex-1 rounded-full ${password && i < score ? level.bar : 'bg-dark-elevated'}`} />
          ))}
        </div>
        {password && <span className={`text-[11px] font-bold ${level.text}`}>{level.label}</span>}
      </div>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        {checks.map((c) => (
          <li key={c.label} className={c.ok ? 'text-emerald-400' : 'text-slate-500'}>{c.ok ? '✓' : '○'} {c.label}</li>
        ))}
      </ul>
    </div>
  )
}
