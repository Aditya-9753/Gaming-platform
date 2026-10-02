import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, AtSign, Lock, ShieldCheck, User, UserPlus } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { PasswordStrength, checkPassword } from '../../../components/common/PasswordStrength'
import { getApiErrorMessage } from '../../../utils/apiError'

interface RoleRow { id: number; name: string; description: string | null; permissions: string[] }

/** Super admin only: create a staff account (route + API both enforce the role). */
export const AddAdmin: React.FC = () => {
  const navigate = useNavigate()
  const [roles, setRoles] = useState<RoleRow[]>([])
  const [fullName, setFullName] = useState('')
  const [loginId, setLoginId] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [role, setRole] = useState('')
  const [idStatus, setIdStatus] = useState<{ checking: boolean; available?: boolean; reason?: string | null }>({ checking: false })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    apiClient.get<RoleRow[]>('/admin/roles')
      .then(({ data }) => {
        const staffRoles = data.filter((r) => r.name !== 'USER' && r.name !== 'SUPERADMIN')
        setRoles(staffRoles)
        setRole((current) => current || staffRoles.find((r) => r.name === 'ADMIN')?.name || staffRoles[0]?.name || '')
      })
      .catch((error) => showToast({ title: 'Roles unavailable', message: getApiErrorMessage(error, 'Only the super admin can add admins.'), type: 'error' }))
  }, [])

  // Live login-ID uniqueness check (same rule as the API: case-insensitive)
  useEffect(() => {
    const candidate = loginId.trim()
    if (candidate.length < 3) { setIdStatus({ checking: false }); return }
    setIdStatus({ checking: true })
    const timer = window.setTimeout(() => {
      apiClient.get<{ available: boolean; reason: string | null }>('/auth/username-available', { params: { username: candidate } })
        .then(({ data }) => setIdStatus({ checking: false, available: data.available, reason: data.reason }))
        .catch(() => setIdStatus({ checking: false }))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [loginId])

  const passwordOk = checkPassword(password).valid
  const matches = password.length > 0 && password === confirm
  const selected = roles.find((r) => r.name === role)
  const canSubmit = fullName.trim().length >= 2 && idStatus.available !== false && loginId.trim().length >= 3 && email.includes('@') && passwordOk && matches && Boolean(role)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSaving(true)
    try {
      await apiClient.post('/admin/admins', { full_name: fullName.trim(), username: loginId.trim(), email: email.trim(), password, role })
      showToast({ title: 'Admin created', message: `${fullName.trim()} (${loginId.trim()}) can now sign in. Share the password privately.`, type: 'success', duration: 8000 })
      navigate('/admin/admin-users')
    } catch (error) {
      showToast({ title: 'Could not create admin', message: getApiErrorMessage(error, 'Check the details and try again.'), type: 'error', duration: 8000 })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <button type="button" onClick={() => navigate('/admin/admin-users')} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />Back to staff list</button>
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-black text-white"><UserPlus className="h-6 w-6 text-purple-400" />Add New Admin</h1>
        <p className="text-xs text-slate-400">Create a staff account. The password is stored only as an Argon2 hash, and the creation is written to the audit log with your name, the time and your IP.</p>
      </div>

      <form onSubmit={(e) => void submit(e)} className="space-y-5 rounded-2xl border border-dark-border bg-dark-card p-5 sm:p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={100} leftElement={<User className="h-4 w-4 text-slate-400" />} required />
          <Input
            label="Login ID"
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            minLength={3}
            maxLength={50}
            pattern="[A-Za-z0-9_]+"
            autoCapitalize="none"
            spellCheck={false}
            leftElement={<AtSign className="h-4 w-4 text-slate-400" />}
            error={idStatus.available === false ? (idStatus.reason || 'This login ID is taken') : undefined}
            helperText={idStatus.checking ? 'Checking…' : idStatus.available ? '✓ Available' : 'Letters, numbers and underscore'}
            required
          />
        </div>
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" helperText="Used for the admin's email verification codes." required />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Input label="Password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} leftElement={<Lock className="h-4 w-4 text-slate-400" />} required />
            <PasswordStrength password={password} />
          </div>
          <Input
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            leftElement={<Lock className="h-4 w-4 text-slate-400" />}
            error={confirm && !matches ? 'Passwords do not match' : undefined}
            helperText={matches ? '✓ Passwords match' : undefined}
            required
          />
        </div>

        <label className="flex flex-col gap-1.5 text-xs font-semibold text-slate-300">Role
          <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded-xl border border-dark-border bg-dark-elevated px-3.5 py-2.5 text-sm text-white" required>
            {roles.map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
          </select>
        </label>
        {selected && (
          <div className="rounded-xl bg-dark-elevated p-3 text-xs">
            <p className="flex items-center gap-1.5 font-bold text-white"><ShieldCheck className="h-4 w-4 text-purple-400" />{selected.name} can:</p>
            <p className="mt-1 text-slate-400">{selected.description}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {selected.permissions.length ? selected.permissions.map((p) => <span key={p} className="rounded bg-dark-card px-1.5 py-0.5 font-mono text-[10px] text-purple-300">{p}</span>) : <span className="text-slate-500">No permissions yet — set them on the Roles page.</span>}
            </div>
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => navigate('/admin/admin-users')}>Cancel</Button>
          <Button type="submit" isLoading={saving} disabled={!canSubmit} leftIcon={<UserPlus className="h-4 w-4" />}>Create admin</Button>
        </div>
      </form>
    </div>
  )
}
