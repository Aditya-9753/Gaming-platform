import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Mail, Send } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'
import { useAuthStore } from '../../../store/auth.store'
import { getApiErrorMessage } from '../../../utils/apiError'

interface SendResponse { sent_to: string; resend_in: number; sent: boolean }

const Step: React.FC<{ n: number; title: string; children: React.ReactNode }> = ({ n, title, children }) => (
  <div className="flex gap-3 text-left">
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-sm font-black text-purple-300">{n}</span>
    <div className="min-w-0 flex-1 space-y-2">
      <p className="text-sm font-bold text-white">{title}</p>
      {children}
    </div>
  </div>
)

/** Admin two-step verification: a fresh 6-digit code is emailed on every sign-in. */
export const Setup2FA: React.FC = () => {
  const navigate = useNavigate()
  const { user, accessToken, setAuth } = useAuthStore()
  const [email, setEmail] = useState(user?.email ?? '')
  const [code, setCode] = useState('')
  const [sentTo, setSentTo] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [done, setDone] = useState(Boolean(user?.has2FA && !user?.requires2FASetup))

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  const sendCode = async () => {
    setSending(true)
    try {
      const { data } = await apiClient.post<SendResponse>('/auth/2fa/email/send', { email: email.trim() || undefined })
      setSentTo(data.sent_to)
      setCooldown(data.resend_in)
      showToast({ title: data.sent ? 'Code sent' : 'Code already sent', message: `Check ${data.sent_to} (and the Spam folder).`, type: 'success' })
    } catch (error) {
      showToast({ title: 'Could not send code', message: getApiErrorMessage(error, 'Please try again.'), type: 'error', duration: 8000 })
    } finally {
      setSending(false)
    }
  }

  const verify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (code.length < 6) return
    setVerifying(true)
    try {
      const { data } = await apiClient.post<{ email: string }>('/auth/2fa/email/verify', { code })
      // Clear the "must enrol" flag so the admin guard stops sending us back here
      if (user && accessToken) setAuth({ ...user, email: data.email, has2FA: true, requires2FASetup: false }, accessToken)
      setDone(true)
      showToast({ title: 'Email verification on', message: 'Each sign-in will now email you a fresh code.', type: 'success', duration: 7000 })
    } catch (error) {
      showToast({ title: 'Code rejected', message: getApiErrorMessage(error, 'Enter the latest code from the email.'), type: 'error' })
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Two-Step Verification</h1>
        <p className="text-xs text-slate-400">Every admin sign-in sends a new 6-digit code to your email. Only you can open the admin panel, even if someone knows the password.</p>
      </div>

      <div className="space-y-6 rounded-2xl border border-dark-border bg-dark-card p-5 shadow-xl sm:p-6">
        {done ? (
          <div className="space-y-3 py-6 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h3 className="text-lg font-bold text-white">Email verification is active</h3>
            <p className="text-xs text-slate-400">Next time you sign in, enter your password, then the code we email to {user?.email ?? 'you'}.</p>
            <Button type="button" onClick={() => navigate('/admin/dashboard')}>Open admin dashboard</Button>
          </div>
        ) : (
          <>
            <Step n={1} title="Where should codes go?">
              <Input type="email" label="Email address" value={email} onChange={(e) => setEmail(e.target.value)} leftElement={<Mail className="h-4 w-4 text-slate-400" />} placeholder="you@gmail.com" />
              <Button type="button" variant="secondary" isLoading={sending} disabled={cooldown > 0 || !email.trim()} leftIcon={<Send className="h-4 w-4" />} onClick={() => void sendCode()}>
                {cooldown > 0 ? `Resend in ${cooldown}s` : sentTo ? 'Resend code' : 'Send code'}
              </Button>
              {sentTo && <p className="text-xs text-emerald-400">Code sent to {sentTo}. It expires in 10 minutes — check the Spam folder too.</p>}
            </Step>

            <Step n={2} title="Enter the 6-digit code from the email">
              <form onSubmit={verify} className="space-y-3">
                <Input
                  placeholder="123456"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  autoComplete="one-time-code"
                  aria-label="6-digit verification code"
                  disabled={!sentTo}
                  required
                />
                <Button type="submit" variant="primary" className="w-full font-bold" disabled={!sentTo || code.length < 6} isLoading={verifying}>
                  Verify & turn on
                </Button>
              </form>
            </Step>
          </>
        )}
      </div>
    </div>
  )
}
