import React, { useState } from 'react'
import { CheckCircle2, KeyRound } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'
import { useAuthStore } from '../../../store/auth.store'

export const Setup2FA: React.FC = () => {
  const { user, accessToken, setAuth } = useAuthStore()
  const [token, setToken] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [isConfigured, setIsConfigured] = useState(false)
  const [secret, setSecret] = useState('')
  const [uri, setUri] = useState('')

  const handleSetup = async () => {
    try {
      const { data } = await apiClient.post<{ secret: string; provisioning_uri: string }>('/auth/totp/setup')
      setSecret(data.secret)
      setUri(data.provisioning_uri)
    } catch {
      showToast({ title: '2FA setup failed', message: 'The server could not prepare authenticator setup.', type: 'error' })
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (token.length < 6) return
    setIsVerifying(true)
    try {
      await apiClient.post('/auth/totp/verify', { code: token })
      if (user && accessToken) setAuth({ ...user, has2FA: true }, accessToken)
      setIsConfigured(true)
      showToast({ title: '2FA Enabled', message: 'TOTP authentication active for your account.', type: 'success' })
    } catch {
      showToast({ title: 'Code rejected', message: 'Enter the current six-digit code from your authenticator.', type: 'error' })
    } finally {
      setIsVerifying(false)
    }
  }

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <div>
        <h1 className="text-2xl font-black text-white">Two-Factor Authentication</h1>
        <p className="text-xs text-slate-400">Secure staff administrative operations with Google Authenticator or Authy</p>
      </div>

      <div className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-5 text-center">
        {isConfigured ? (
          <div className="space-y-3 py-6">
            <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 mx-auto flex items-center justify-center text-emerald-400">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-white">2FA is Fully Active</h3>
            <p className="text-xs text-slate-400">Your account requires an authenticator code on each sign-in.</p>
          </div>
        ) : (
          <>
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-purple-500/20 bg-purple-500/10 text-purple-400">
              <KeyRound className="h-8 w-8" />
            </div>
            <p className="text-xs text-slate-400">
              Add this account in your authenticator app using the setup link or enter the secret manually.
            </p>

            <div className="space-y-1">
              <span className="text-xs text-slate-400">Secret Key (Manual Entry):</span>
              <code className="text-xs font-mono font-bold text-purple-400 block bg-dark-elevated py-1 px-2 rounded-lg">
                {secret || 'Generate your personal key below'}
              </code>
            </div>
            {uri && <a href={uri} className="block break-all text-left text-[10px] text-emerald-400 underline">Open authenticator setup link</a>}
            {!secret && <Button type="button" variant="secondary" onClick={() => void handleSetup()}>Generate authenticator secret</Button>}

            <form onSubmit={handleVerify} className="space-y-3 pt-3">
              <Input
                label="6-Digit Verification Code"
                placeholder="123456"
                maxLength={6}
                value={token}
                onChange={(e) => setToken(e.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                pattern="[0-9]{6}"
                autoComplete="one-time-code"
                required
              />

              <Button type="submit" variant="primary" className="w-full font-bold" disabled={!secret} isLoading={isVerifying}>
                Verify & Activate 2FA
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
