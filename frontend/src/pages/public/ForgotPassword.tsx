import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { UserRound, ArrowLeft, CheckCircle2 } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { authApi } from '../../services/auth.api'
import { getApiErrorMessage } from '../../utils/apiError'
import { t as tr } from '../../i18n'

export const ForgotPassword: React.FC = () => {
  const [identifier, setIdentifier] = useState('')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)
    try {
      const { sent_to } = await authApi.forgotPassword(identifier)
      setSentTo(sent_to)
    } catch (err) {
      setError(getApiErrorMessage(err, tr('Password reset could not be requested. Please try again.')))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" />
          <span>{tr('Back to Login')}</span>
        </Link>

        {sentTo ? (
          <div className="text-center space-y-4 py-4">
            <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 mx-auto flex items-center justify-center text-emerald-400">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h3 className="text-xl font-bold text-white">{tr('Reset Link Sent')}</h3>
              <p className="text-sm text-slate-300">{tr('We emailed a reset link to')} <b className="text-white">{sentTo}</b></p>
              <p className="text-xs text-slate-400">{tr('Open it within 1 hour to choose a new password. Check the spam folder if it is not in your inbox.')}</p>
            </div>
            <button type="button" onClick={() => setSentTo(null)} className="text-xs font-bold text-emerald-400 hover:underline">{tr('Send again')}</button>
          </div>
        ) : (
          <>
            <div>
              <h2 className="text-2xl font-black text-white">{tr('Reset Password')}</h2>
              <p className="text-xs text-slate-400 mt-1">
                {tr('Enter your mobile number or email. We will email a link to set a new password.')}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label={tr('Mobile number or email')}
                autoComplete="username"
                placeholder="9876543210"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                leftElement={<UserRound className="w-4 h-4 text-slate-400" />}
                error={error || undefined}
                required
              />

              <Button type="submit" variant="primary" className="w-full font-bold py-3" isLoading={isLoading}>
                {tr('Send Reset Link')}
              </Button>
              <p className="text-[11px] text-slate-500">
                {tr('The link goes to the email saved in your profile. No email on your account? Contact support.')}
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
