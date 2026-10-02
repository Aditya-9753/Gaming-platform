import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ArrowLeft, CheckCircle2 } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { authApi } from '../../services/auth.api'
import { showToast } from '../../components/common/Toast'

export const ForgotPassword: React.FC = () => {
  const [email, setEmail] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    try {
      await authApi.forgotPassword(email)
      setIsSubmitted(true)
    } catch {
      showToast({ title: 'Request failed', message: 'Password reset could not be requested. Please try again.', type: 'error' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Login</span>
        </Link>

        {isSubmitted ? (
          <div className="text-center space-y-4 py-4">
            <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 mx-auto flex items-center justify-center text-emerald-400">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-white">Reset Link Sent</h3>
              <p className="text-xs text-slate-400 mt-1">
                If an account exists for {email}, a password reset link has been dispatched.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div>
              <h2 className="text-2xl font-black text-white">Reset Password</h2>
              <p className="text-xs text-slate-400 mt-1">
                Enter your registered email address to receive recovery instructions.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="Email Address"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                leftElement={<Mail className="w-4 h-4 text-slate-400" />}
                required
              />

              <Button type="submit" variant="primary" className="w-full font-bold py-3" isLoading={isLoading}>
                Send Reset Link
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
