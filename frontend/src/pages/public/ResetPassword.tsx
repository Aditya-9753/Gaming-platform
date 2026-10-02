import React, { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { showToast } from '../../components/common/Toast'
import { authApi } from '../../services/auth.api'

export const ResetPassword: React.FC = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password !== confirmPassword) {
      showToast({ title: 'Passwords do not match', type: 'error' })
      return
    }
    const token = searchParams.get('token')
    if (!token) {
      showToast({ title: 'Invalid reset link', message: 'The password reset token is missing from this link.', type: 'error' })
      return
    }
    setIsLoading(true)
    try {
      await authApi.resetPassword(token, password)
      showToast({ title: 'Password Reset', message: 'You can now sign in with your new password.', type: 'success' })
      navigate('/login')
    } catch {
      showToast({ title: 'Password reset failed', message: 'The reset link may have expired or the password is invalid.', type: 'error' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <div>
          <h2 className="text-2xl font-black text-white">Create New Password</h2>
          <p className="text-xs text-slate-400 mt-1">
            Ensure your new password has at least 8 characters.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="New Password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            leftElement={<Lock className="w-4 h-4 text-slate-400" />}
            required
          />

          <Input
            label="Confirm Password"
            type="password"
            placeholder="••••••••"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            leftElement={<Lock className="w-4 h-4 text-slate-400" />}
            required
          />

          <Button type="submit" variant="primary" className="w-full font-bold py-3" isLoading={isLoading}>
            Update Password
          </Button>
        </form>

        <p className="text-center text-xs text-slate-400">
          Remember your password?{' '}
          <Link to="/login" className="text-emerald-400 font-bold hover:underline">
            Back to Login
          </Link>
        </p>
      </div>
    </div>
  )
}
