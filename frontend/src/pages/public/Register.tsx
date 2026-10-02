import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lock, User, ShieldAlert, ArrowRight } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { useAuthStore } from '../../store/auth.store'
import { authApi } from '../../services/auth.api'
import { showToast } from '../../components/common/Toast'
import { apiClient } from '../../services/api'

const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#^])[A-Za-z\d@$!%*?&_\-#^]{8,128}$/

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
      if (field === 'password') return 'Password must be 8–128 characters and include uppercase, lowercase, a number, and one allowed symbol: @$!%*?&_-#^.'
      if (field === 'username') return 'Username must be 3–50 characters using only letters, numbers, and underscores.'
      if (field === 'age_confirmed') return 'Confirm that you meet the legal age requirement.'
      return message || body?.error?.message || 'Please check your details and try again.'
    }).join(' ')
  }

  if (error.response?.status === 409) return body?.error?.message || 'That username is already taken.'
  if (error.response?.status === 429) return 'Too many registration attempts. Please wait a few minutes and try again.'
  if (error.response && error.response.status >= 500) {
    return 'The registration server could not save your account. The server administrator should check that PostgreSQL is running and DATABASE_URL is correct.'
  }
  if (!error.response) {
    return 'Cannot reach the registration server. Check that the backend is running and try again.'
  }
  return body?.error?.message || 'Registration could not be completed. Please try again.'
}

export const Register: React.FC = () => {
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [is18, setIs18] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [nameStatus, setNameStatus] = useState<{ checking: boolean; available?: boolean; reason?: string | null }>({ checking: false })

  // Live uniqueness check (case-insensitive on the server)
  useEffect(() => {
    const candidate = username.trim()
    if (candidate.length < 3) { setNameStatus({ checking: false }); return }
    setNameStatus({ checking: true })
    const timer = window.setTimeout(() => {
      apiClient.get<{ available: boolean; reason: string | null }>('/auth/username-available', { params: { username: candidate } })
        .then(({ data }) => setNameStatus({ checking: false, available: data.available, reason: data.reason }))
        .catch(() => setNameStatus({ checking: false }))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [username])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!/^[a-zA-Z0-9_]{3,50}$/.test(username)) {
      showToast({ title: 'Invalid username', message: 'Use 3–50 letters, numbers, or underscores.', type: 'error' })
      return
    }
    if (!PASSWORD_PATTERN.test(password)) {
      showToast({ title: 'Invalid password', message: 'Use 8–128 characters with uppercase, lowercase, a number, and one of: @$!%*?&_-#^.', type: 'error' })
      return
    }
    if (nameStatus.available === false) {
      showToast({ title: 'Username unavailable', message: nameStatus.reason || 'Pick a different username.', type: 'error' })
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
      const { access_token } = await authApi.register(username, password, is18)
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

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-black text-white">Create Account</h2>
          <p className="text-xs text-slate-400">Pick a username and password, that's all you need</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input label="Username" autoComplete="username" minLength={3} maxLength={50} pattern="[A-Za-z0-9_]+" title="Use 3–50 letters, numbers, or underscores." value={username} onChange={(e) => setUsername(e.target.value)} leftElement={<User className="w-4 h-4 text-slate-400" />} error={nameStatus.available === false ? (nameStatus.reason || 'Username is already taken') : undefined} helperText={nameStatus.checking ? 'Checking availability…' : nameStatus.available ? '✓ Username is available' : 'Your unique player name (letters, numbers, underscore)'} required />
          <Input label="Password" type="password" autoComplete="new-password" minLength={8} maxLength={128} helperText="8–128 characters; include uppercase, lowercase, a number, and one of: @$!%*?&_-#^." value={password} onChange={(e) => setPassword(e.target.value)} leftElement={<Lock className="w-4 h-4 text-slate-400" />} required />
          <Input label="Confirm password" type="password" autoComplete="new-password" minLength={8} maxLength={128} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} leftElement={<Lock className="w-4 h-4 text-slate-400" />} error={confirmPassword && confirmPassword !== password ? 'Passwords do not match' : undefined} required />
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
