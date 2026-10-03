import React, { useEffect, useState } from 'react'
import { User, Mail, Shield } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { showToast } from '../../components/common/Toast'
import { useAuthStore } from '../../store/auth.store'
import { useWalletStore } from '../../store/wallet.store'
import { formatPaiseToRupee } from '../../utils/formatters'
import { userApi } from '../../services/user.api'
import { apiClient } from '../../services/api'

export const Profile: React.FC = () => {
  const { user } = useAuthStore()
  const { setAuth, accessToken } = useAuthStore()
  const { balance } = useWalletStore()

  const [username, setUsername] = useState(user?.username || '')
  const [email, setEmail] = useState(user?.email || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<'profile' | 'security'>('profile')

  // Live uniqueness check (same endpoint the sign-up form uses)
  const [nameStatus, setNameStatus] = useState<{ checking: boolean; available: boolean | null; reason: string | null }>({ checking: false, available: null, reason: null })
  const trimmedName = username.trim()
  const nameChanged = !!user && trimmedName.toLowerCase() !== user.username.toLowerCase()
  useEffect(() => {
    if (!nameChanged) { setNameStatus({ checking: false, available: null, reason: null }); return }
    if (!/^[A-Za-z0-9_]{3,50}$/.test(trimmedName)) {
      setNameStatus({ checking: false, available: false, reason: 'Use 3–50 letters, numbers or _' })
      return
    }
    setNameStatus((s) => ({ ...s, checking: true }))
    const timer = setTimeout(() => {
      apiClient.get<{ available: boolean; reason: string | null }>('/auth/username-available', { params: { username: trimmedName } })
        .then(({ data }) => setNameStatus({ checking: false, available: data.available, reason: data.reason }))
        .catch(() => setNameStatus({ checking: false, available: null, reason: null }))
    }, 400)
    return () => clearTimeout(timer)
  }, [trimmedName, nameChanged])

  useEffect(() => {
    if (user) {
      setUsername(user.username)
      setEmail(user.email || '')
    }
  }, [user])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      const profile = await userApi.updateProfile({ username: trimmedName, email })
      if (user && accessToken) setAuth({ ...user, username: profile.username, email: profile.email }, accessToken)
      showToast({ title: 'Profile Updated', message: 'Your information has been saved.', type: 'success' })
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status
      showToast({
        title: 'Profile update failed',
        message: status === 409 ? 'That username or email is already taken. Try another one.' : 'The server did not save your profile changes.',
        type: 'error',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handlePasswordUpdate = async () => {
    setIsChangingPassword(true)
    try {
      await apiClient.post('/users/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword('')
      setNewPassword('')
      showToast({ title: 'Password updated', type: 'success' })
    } catch {
      showToast({ title: 'Password update failed', message: 'Verify your current password and new password.', type: 'error' })
    } finally {
      setIsChangingPassword(false)
    }
  }

  const stats = [
    { label: 'Real Balance', value: formatPaiseToRupee(balance.realBalancePaise), color: 'text-emerald-400' },
    { label: 'Bonus Balance', value: formatPaiseToRupee(balance.bonusBalancePaise), color: 'text-purple-400' },
    { label: 'VIP Level', value: '—', color: 'text-amber-400' },
  ]

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <User className="w-6 h-6 text-emerald-400" />
        <div>
          <h2 className="text-2xl font-black text-white">My Profile</h2>
          <p className="text-xs text-slate-400">Manage your account information and password</p>
        </div>
      </div>

      {/* Profile Card */}
      <div className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl">
        <div className="flex items-center gap-5 mb-6">
          <div className="relative">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-2xl font-black text-dark-bg shadow-xl">
              {(user?.username || 'P')[0].toUpperCase()}
            </div>
          </div>

          <div>
            <h3 className="text-xl font-black text-white">{user?.username}</h3>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              {user?.role?.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {stats.map((s, i) => (
            <div key={i} className="p-3 rounded-xl bg-dark-elevated border border-dark-border text-center">
              <span className={`text-sm font-black block ${s.color}`}>{s.value}</span>
              <span className="text-[10px] text-slate-500 mt-0.5 block">{s.label}</span>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div className="grid grid-cols-2 gap-2 p-1 bg-dark-elevated rounded-xl mb-5">
          <button
            onClick={() => setActiveTab('profile')}
            className={`py-2 rounded-lg text-xs font-bold transition-all ${
              activeTab === 'profile' ? 'bg-emerald-500 text-dark-bg shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            Personal Info
          </button>
          <button
            onClick={() => setActiveTab('security')}
            className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-bold transition-all ${
              activeTab === 'security' ? 'bg-emerald-500 text-dark-bg shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            <span>Security</span>
          </button>
        </div>

        {activeTab === 'profile' ? (
          <form onSubmit={handleSave} className="space-y-4">
            <Input
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value.replace(/\s/g, ''))}
              leftElement={<User className="w-4 h-4" />}
              maxLength={50}
              error={nameChanged && !nameStatus.checking && nameStatus.available === false ? `✗ ${nameStatus.reason || 'Username not available'}` : undefined}
              success={nameChanged && !nameStatus.checking && nameStatus.available ? '✓ This username is available' : undefined}
            />
            <Input
              label="Email Address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              leftElement={<Mail className="w-4 h-4" />}
              placeholder="you@example.com"
            />
            <Button type="submit" variant="primary" className="w-full font-bold" isLoading={isSaving} disabled={nameChanged && nameStatus.available !== true}>
              Save Changes
            </Button>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-dark-elevated border border-dark-border space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <Shield className="w-4 h-4 text-emerald-400" />
                <span className="font-bold text-white">Change Password</span>
              </div>
              <div className="space-y-3">
                <Input label="Current Password" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
                <Input label="New Password" type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                <Button variant="primary" size="sm" className="w-full font-bold" isLoading={isChangingPassword} disabled={!currentPassword || !newPassword} onClick={() => void handlePasswordUpdate()}>
                  Update Password
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
