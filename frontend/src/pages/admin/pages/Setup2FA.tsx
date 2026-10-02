import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'
import { CheckCircle2, Copy, KeyRound, Smartphone } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'
import { useAuthStore } from '../../../store/auth.store'
import { getApiErrorMessage } from '../../../utils/apiError'

/** Groups of four characters are much easier to type into a phone. */
const groupSecret = (secret: string) => secret.replace(/(.{4})/g, '$1 ').trim()

const Step: React.FC<{ n: number; title: string; children: React.ReactNode }> = ({ n, title, children }) => (
  <div className="flex gap-3 text-left">
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-sm font-black text-purple-300">{n}</span>
    <div className="min-w-0 flex-1 space-y-2">
      <p className="text-sm font-bold text-white">{title}</p>
      {children}
    </div>
  </div>
)

export const Setup2FA: React.FC = () => {
  const navigate = useNavigate()
  const { user, accessToken, setAuth } = useAuthStore()
  const [token, setToken] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isConfigured, setIsConfigured] = useState(Boolean(user?.has2FA))
  const [secret, setSecret] = useState('')
  const [uri, setUri] = useState('')
  const [qr, setQr] = useState('')

  // QR is drawn in the browser — the secret never leaves this page
  useEffect(() => {
    if (!uri) { setQr(''); return }
    QRCode.toDataURL(uri, { width: 220, margin: 1, errorCorrectionLevel: 'M' })
      .then(setQr)
      .catch(() => setQr(''))
  }, [uri])

  const handleSetup = async () => {
    setIsGenerating(true)
    try {
      const { data } = await apiClient.post<{ secret: string; provisioning_uri: string }>('/auth/totp/setup')
      setSecret(data.secret)
      setUri(data.provisioning_uri)
      setToken('')
    } catch (error) {
      showToast({ title: '2FA setup failed', message: getApiErrorMessage(error, 'The server could not prepare authenticator setup.'), type: 'error' })
    } finally {
      setIsGenerating(false)
    }
  }

  const copySecret = async () => {
    try {
      await navigator.clipboard.writeText(secret)
      showToast({ title: 'Copied', message: 'Secret key copied to the clipboard.', type: 'success', duration: 2000 })
    } catch {
      showToast({ title: 'Copy failed', message: 'Select the key and copy it manually.', type: 'warning' })
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (token.length < 6) return
    setIsVerifying(true)
    try {
      await apiClient.post('/auth/totp/verify', { code: token })
      // Clear the "must enrol" flag too, otherwise the admin guard keeps sending us back here
      if (user && accessToken) setAuth({ ...user, has2FA: true, requires2FASetup: false }, accessToken)
      setIsConfigured(true)
      showToast({ title: '2FA enabled', message: 'From now on, sign in with your password + the 6-digit code.', type: 'success', duration: 7000 })
    } catch (error) {
      showToast({ title: 'Code rejected', message: getApiErrorMessage(error, 'Enter the current 6-digit code shown in your authenticator app.'), type: 'error' })
    } finally {
      setIsVerifying(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Two-Factor Authentication</h1>
        <p className="text-xs text-slate-400">Protect the admin account with a 6-digit code from Google Authenticator, Microsoft Authenticator or Authy.</p>
      </div>

      <div className="space-y-6 rounded-2xl border border-dark-border bg-dark-card p-5 shadow-xl sm:p-6">
        {isConfigured ? (
          <div className="space-y-3 py-6 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h3 className="text-lg font-bold text-white">2FA is active</h3>
            <p className="text-xs text-slate-400">Every sign-in now needs your password and the current code from the app. Keep the phone safe.</p>
            <Button type="button" onClick={() => navigate('/admin/dashboard')}>Open admin dashboard</Button>
          </div>
        ) : (
          <>
            <Step n={1} title="Install an authenticator app on your phone">
              <p className="flex items-center gap-1.5 text-xs text-slate-400"><Smartphone className="h-3.5 w-3.5" />Google Authenticator, Microsoft Authenticator or Authy (Play Store / App Store).</p>
            </Step>

            <Step n={2} title="Create your personal key">
              {!secret ? (
                <Button type="button" variant="secondary" isLoading={isGenerating} leftIcon={<KeyRound className="h-4 w-4" />} onClick={() => void handleSetup()}>Generate authenticator key</Button>
              ) : (
                <p className="text-xs text-emerald-400">Key created. Don't share it with anyone.</p>
              )}
            </Step>

            {secret && (
              <Step n={3} title="Add it to the app">
                <p className="text-xs text-slate-400">In the app tap <b className="text-white">+</b> → <b className="text-white">Scan a QR code</b> and scan this:</p>
                {qr && <img src={qr} alt="Authenticator QR code" className="h-48 w-48 rounded-xl bg-white p-2" />}
                <p className="text-xs text-slate-400">Can't scan? Choose <b className="text-white">Enter a setup key</b> instead: account name <b className="text-white">{user?.username ?? 'superadmin'}</b>, key type <b className="text-white">Time based</b>, and this key:</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded-lg bg-dark-elevated px-3 py-2 text-left font-mono text-sm font-bold tracking-wider text-purple-300">{groupSecret(secret)}</code>
                  <button type="button" onClick={() => void copySecret()} aria-label="Copy secret key" className="rounded-lg bg-dark-elevated p-2 text-slate-300 hover:text-white"><Copy className="h-4 w-4" /></button>
                </div>
                {uri && <a href={uri} className="inline-block text-xs text-emerald-400 underline">On this phone? Tap here to open the authenticator app</a>}
              </Step>
            )}

            <Step n={secret ? 4 : 3} title="Type the 6-digit code shown in the app">
              <form onSubmit={handleVerify} className="space-y-3">
                <Input
                  placeholder="123456"
                  maxLength={6}
                  value={token}
                  onChange={(e) => setToken(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  autoComplete="one-time-code"
                  aria-label="6-digit verification code"
                  disabled={!secret}
                  required
                />
                <p className="text-[11px] text-slate-500">The code changes every 30 seconds — enter the one currently shown.</p>
                <Button type="submit" variant="primary" className="w-full font-bold" disabled={!secret || token.length < 6} isLoading={isVerifying}>
                  Verify & activate 2FA
                </Button>
              </form>
            </Step>
          </>
        )}
      </div>
    </div>
  )
}
