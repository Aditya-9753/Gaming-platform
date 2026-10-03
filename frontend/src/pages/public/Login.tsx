import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lock, User, ArrowRight, ShieldCheck, KeyRound } from 'lucide-react'
import { BrandLogo } from '../../components/common/BrandLogo'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { useAuthStore } from '../../store/auth.store'
import { authApi } from '../../services/auth.api'
import { showToast } from '../../components/common/Toast'
import { isStaffRole } from '../../types/auth.types'

const getLoginError = (error: unknown): string => {
  if (!axios.isAxiosError(error)) return 'Could not sign in. Check your connection and try again.'
  if (!error.response) return 'Cannot reach the server. Check that the backend is running on port 8000.'
  const body = error.response?.data as { error?: { message?: string } } | undefined
  const message = body?.error?.message
  if (error.response?.status === 401) return message || 'Username or password is incorrect.'
  if (error.response?.status === 403) return message || 'This account is inactive or access is restricted.'
  if (error.response?.status === 429) return 'Too many sign-in attempts. Wait a few minutes before trying again.'
  return message || 'Could not sign in. Please try again.'
}

export const Login: React.FC = () => {
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  // 'email' = a one-time code was emailed; 'app' = authenticator app code
  const [codeMode, setCodeMode] = useState<'email' | 'app'>('app')
  const [codeNotice, setCodeNotice] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const signIn = async (code?: string) => {
    setIsLoading(true)
    try {
      const { access_token } = await authApi.login(username, password, code || undefined)
      setAccessToken(access_token)
      const user = await authApi.getCurrentUser()
      setAuth(user, access_token)
      showToast({ title: 'Welcome back!', message: 'Signed in successfully.', type: 'success' })
      navigate(isStaffRole(user.role)
        ? user.requires2FASetup ? '/admin/2fa' : '/admin/dashboard'
        : '/dashboard')
    } catch (error) {
      const message = getLoginError(error)
      if (/verification code sent/i.test(message)) {
        // Password was correct; a fresh code is on its way to the admin's inbox
        setCodeMode('email')
        setNeedsTotp(true)
        setTotpCode('')
        setCodeNotice(message)
        showToast({ title: 'Check your email', message, type: 'info', duration: 7000 })
        return
      }
      if (/authenticator code|totp code/i.test(message)) { setCodeMode('app'); setNeedsTotp(true) }
      showToast({ title: 'Sign in failed', message, type: 'error', duration: 7000 })
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    void signIn(totpCode)
  }

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <BrandLogo wordmark className="flex justify-center" textClassName="text-2xl font-black tracking-tight" />
          <h2 className="text-2xl font-black text-white">Welcome Back</h2>
          <p className="text-xs text-slate-400">Sign in with your username and password</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input label="Username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(e) => setUsername(e.target.value)} leftElement={<User className="w-4 h-4 text-slate-400" />} required />
          <Input label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} leftElement={<Lock className="w-4 h-4 text-slate-400" />} required />
          {needsTotp ? (
            <div className="space-y-2">
              {codeMode === 'email' && codeNotice && (
                <p className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">{codeNotice}</p>
              )}
              <Input
                label={codeMode === 'email' ? 'Verification code (check your email)' : 'Authenticator code'}
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                autoFocus
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                leftElement={<KeyRound className="w-4 h-4 text-slate-400" />}
                helperText={codeMode === 'email' ? 'Enter the 6-digit code from the email. It expires in 10 minutes. Check the Spam folder if it is not in your inbox.' : 'Enter the current six-digit code from your authenticator app.'}
                required
              />
              {codeMode === 'email' && (
                <button type="button" disabled={isLoading} onClick={() => { setTotpCode(''); void signIn() }} className="text-xs font-semibold text-emerald-400 hover:underline disabled:opacity-50">Didn't get it? Resend code</button>
              )}
            </div>
          ) : null}
          <div className="flex items-center justify-between text-xs">
            <button type="button" onClick={() => setNeedsTotp((value) => !value)} className="text-slate-400 hover:text-slate-200">{needsTotp ? 'Hide code' : 'Have a verification code?'}</button>
            <Link to="/forgot-password" className="text-emerald-400 hover:underline font-semibold">Forgot password?</Link>
          </div>
          <Button type="submit" variant="primary" className="w-full font-black py-3" isLoading={isLoading} rightIcon={<ArrowRight className="w-4 h-4" />}>Sign In</Button>
        </form>
        <p className="text-center text-xs text-slate-400 pt-2">
          Don't have an account? <Link to="/register" className="text-emerald-400 font-bold hover:underline">Register</Link>
        </p>
        <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          <span>Secure server-backed authentication</span>
        </div>
      </div>
    </div>
  )
}
