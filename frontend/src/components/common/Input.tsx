import React, { forwardRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  /** Green confirmation shown under the field (e.g. "username available") */
  success?: string
  helperText?: string
  leftElement?: React.ReactNode
  rightElement?: React.ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, success, helperText, leftElement, rightElement, className = '', type, ...props }, ref) => {
    // Password fields get a show/hide button unless the caller supplies its own right element
    const [reveal, setReveal] = useState(false)
    const isPassword = type === 'password'
    const toggle = isPassword && !rightElement ? (
      <button
        type="button"
        onClick={() => setReveal((v) => !v)}
        aria-label={reveal ? 'Hide password' : 'Show password'}
        aria-pressed={reveal}
        className="rounded-md p-1 text-slate-400 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
      >
        {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    ) : null
    const right = rightElement ?? toggle
    return (
      <div className="w-full space-y-1.5 text-left">
        {label && (
          <label className="block text-xs font-semibold text-slate-300">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftElement && (
            <div className="absolute left-3.5 flex items-center pointer-events-none text-slate-400">
              {leftElement}
            </div>
          )}
          <input
            ref={ref}
            type={isPassword && reveal ? 'text' : type}
            className={`w-full bg-dark-card border rounded-xl py-2.5 px-3.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 transition-all duration-200 ${
              leftElement ? 'pl-10' : ''
            } ${right ? 'pr-11' : ''} ${
              error
                ? 'border-rose-500 focus:ring-rose-500/30'
                : success
                ? 'border-emerald-500 focus:ring-emerald-500/30'
                : 'border-dark-border focus:border-emerald-500 focus:ring-emerald-500/20'
            } ${className}`}
            {...props}
          />
          {right && (
            <div className="absolute right-2.5 flex items-center text-slate-400">
              {right}
            </div>
          )}
        </div>
        {error ? (
          <p className="text-xs text-rose-400 font-medium">{error}</p>
        ) : success ? (
          <p className="text-xs text-emerald-400 font-medium">{success}</p>
        ) : helperText ? (
          <p className="text-xs text-slate-500">{helperText}</p>
        ) : null}
      </div>
    )
  }
)

Input.displayName = 'Input'

