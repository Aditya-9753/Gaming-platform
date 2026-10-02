import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lock, User, ShieldAlert, ArrowRight, Eye, EyeOff, Check, X, Loader2 } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { useAuthStore } from '../../store/auth.store'
import { authApi } from '../../services/auth.api'
import { showToast } from '../../components/common/Toast'
import { apiClient } from '../../services/api'

// Must match PLAYER_PASSWORD_PATTERN on the server
const USERNAME_PATTERN = /^[a-zA-Z0-9_]{3,50}$/
const passwordChecks = (password: string) => [
  { label: 'At least 8 characters', ok: password.length >= 8 && password.length <= 128 },
  { label: 'At least one letter (a–z or A–Z)', ok: /[A-Za-z]/.test(password) },
  { label: 'At least one number (0–9)', ok: /\d/.test(password) },
]

const getRegistrationError = (error: unknown): string => {
  if (!axios.isAxiosError(error)) return 'Registration could not be completed. Please try again.'

  const body = error.response?.data as {
    error?: { message?: string; details?: Array<{ loc?: Array<string | number>; msg?: string }> }
  } | undefined
  const details = body?.error?.details
  if (Array.isArray(details) && details.length > 0) {
    return details.map((item) => {
      const field = item.loc?.at(-1)
      const message = item.msg?.replace(/^Value error,\s*/i, '')
      if (field === 'password') return 'Password must be at least 8 characters with a letter and a number.'
      if (field === 'username') return 'Username must be 3–50 characters using only letters, numbers, and underscores.'
      if (field === 'age_confirmed') return 'Confirm that you meet the legal age requirement.'
      return message || body?.error?.message || 'Please check your details and try again.'
    }).join(' ')
  }

  if (error.response?.status === 409) return body?.error?.message || 'That username is already taken. Try another one.'
  if (error.response?.status === 429) return 'Too many registration attempts. Please wait a few minutes and try again.'
  if (error.response && error.response.status >= 500) return 'The server could not save your account right now. Please try again in a minute.'
  if (!error.response) return 'Cannot reach the server. Check your internet connection and try again.'
  return body?.error?.message || 'Registration could not be completed. Please try again.'
}

type NameStatus = { checking: boolean; available?: boolean; reason?: string | null; suggestions?: string[] }

export const Register: React.FC = () => {
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [is18, setIs18] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [nameStatus, setNameStatus] = useState<NameStatus>({ checking: false })

  // Live uniqueness check (case-insensitive on the server)
  useEffect(() => {
    const candidate = username.trim()
    if (candidate.length === 0) { setNameStatus({ checking: false }); return }
    setNameStatus({ checking: true })
    const timer = window.setTimeout(() => {
      apiClient.get<{ available: boolean; reason: string | null; suggestions?: string[] }>('/auth/username-available', { params: { username: candidate } })
        .then(({ data }) => setNameStatus({ checking: false, available: data.available, reason: data.reason, suggestions: data.suggestions ?? [] }))
        .catch(() => setNameStatus({ checking: false }))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [username])

  const checks = passwordChecks(password)
  const passwordOk = checks.every((c) => c.ok)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!USERNAME_PATTERN.test(username.trim())) {
      showToast({ title: 'Invalid username', message: 'Use 3–50 letters, numbers or _ (for example Rahul_007).', type: 'error' })
      return
    }
    if (nameStatus.available === false) {
      showToast({ title: 'Username taken', message: 'Try another username, or pick one of the suggestions.', type: 'error' })
      return
    }
    if (!passwordOk) {
      showToast({ title: 'Password too weak', message: 'Use at least 8 characters with a letter and a number.', type: 'error' })
      return
    }
    if (password !== confirmPassword) {
      showToast({ title: 'Passwords do not match', message: 'Re-enter the same password in both fields.', type: 'error' })
      return
    }
    if (!is18) {
      showToast({ title: 'Age restriction', message: 'You must confirm you are of legal age.', type: 'error' })
      return
    }
    setIsLoading(true)
    try {
      const { access_token } = await authApi.register(username.trim(), password, is18)
      setAccessToken(access_token)
      const user = await authApi.getCurrentUser()
      setAuth(user, access_token)
      showToast({ title: 'Account created', message: 'Your account is ready.', type: 'success' })
      navigate('/dashboard')
    } catch (error) {
      showToast({ title: 'Registration failed', message: getRegistrationError(error), type: 'error', duration: 9000 })
    } finally {
      setIsLoading(false)
    }
  }

  const nameIcon = nameStatus.checking
    ? <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
    : nameStatus.available === true ? <Check className="w-4 h-4 text-emerald-400" />
    : nameStatus.available === false ? <X className="w-4 h-4 text-rose-400" /> : undefined
  const nameError = !nameStatus.checking && nameStatus.available === false
    ? (nameStatus.suggestions?.length ? `✗ ${nameStatus.reason}. Try another username.` : `✗ ${nameStatus.reason || 'Username not available'}`)
    : undefined

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-black text-white">Create Account</h2>
          <p className="text-xs text-slate-400">Pick a username and password, that's all you need</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Input
              label="Username" autoComplete="username" maxLength={50} placeholder="e.g. Rahul_007"
              value={username} onChange={(e) => setUsername(e.target.value.replace(/\s/g, ''))}
              leftElement={<User className="w-4 h-4 text-slate-400" />} rightElement={nameIcon}
              error={nameError}
              success={!nameStatus.checking && nameStatus.available ? '✓ Great! This username is available' : undefined}
              helperText={nameStatus.checking ? 'Checking availability…' : 'Examples: Rahul_007, sanu27, King_Khan · 3–50 letters, numbers or _ (no spaces)'}
              required
            />
            {!nameStatus.checking && nameStatus.available === false && (nameStatus.suggestions?.length ?? 0) > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-slate-400">Available:</span>
                {nameStatus.suggestions!.map((s) => (
                  <button key={s} type="button" onClick={() => setUsername(s)}
                    className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 font-semibold text-emerald-300 hover:bg-emerald-500/20">{s}</button>
                ))}
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Input
              label="Password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" maxLength={128} placeholder="e.g. sanu1234"
              value={password} onChange={(e) => setPassword(e.target.value)}
              leftElement={<Lock className="w-4 h-4 text-slate-400" />}
              rightElement={<button type="button" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'} className="text-slate-400 hover:text-white">{showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>}
              required
            />
            <ul className="grid gap-1 text-xs">
              {checks.map((c) => (
                <li key={c.label} className={`flex items-center gap-1.5 ${password ? (c.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-slate-500'}`}>
                  {password && c.ok ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}{c.label}
                </li>
              ))}
            </ul>
          </div>
          <Input
            label="Confirm password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" maxLength={128}
            value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
            leftElement={<Lock className="w-4 h-4 text-slate-400" />}
            error={confirmPassword && confirmPassword !== password ? '✗ Passwords do not match' : undefined}
            success={confirmPassword && confirmPassword === password ? '✓ Passwords match' : undefined}
            required
          />
          <div className="p-3 rounded-xl bg-dark-elevated border border-dark-border">
            <label className="flex items-start gap-2.5 text-xs text-slate-300 cursor-pointer">
              <input type="checkbox" checked={is18} onChange={(e) => setIs18(e.target.checked)} className="mt-0.5 rounded" required />
              <span>I confirm I am of legal age to use this platform.</span>
            </label>
          </div>
          <Button type="submit" variant="primary" className="w-full font-black py-3" isLoading={isLoading} rightIcon={<ArrowRight className="w-4 h-4" />}>Create My Account</Button>
        </form>
        <p className="text-center text-xs text-slate-400">
          Already have an account? <Link to="/login" className="text-emerald-400 font-bold hover:underline">Sign In</Link>
        </p>
        <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 text-center">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>Age eligibility is required to register.</span>
        </div>
      </div>
    </div>
  )
}
