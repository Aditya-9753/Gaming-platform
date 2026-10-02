import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Ban, CheckCircle2, Coins, Pencil, Trash2, UserPlus } from 'lucide-react'
import { DataTable, type Column } from '../components/DataTable'
import { Modal } from '../components/Modal'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { useAuthStore } from '../../../store/auth.store'
import { getApiErrorMessage } from '../../../utils/apiError'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'

interface StaffAdmin {
  id: string
  username: string
  full_name: string | null
  email: string | null
  role: string | null
  is_active: boolean
  totp_enabled: boolean
  last_login_at: string | null
}

interface ActivityItem { id: number; action: string; target_type: string; target_id: string | null; ip_address: string | null; created_at: string; details: Record<string, unknown> | null }

type Dialog =
  | { kind: 'edit'; user: StaffAdmin }
  | { kind: 'credit'; user: StaffAdmin }
  | { kind: 'activity'; user: StaffAdmin }
  | { kind: 'remove'; user: StaffAdmin }
  | null


export const AdminUsers: React.FC = () => {
  const me = useAuthStore((s) => s.user)
  const isSuper = me?.role === 'superadmin'
  const [staff, setStaff] = useState<StaffAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const [roleNames, setRoleNames] = useState<string[]>(['ADMIN', 'SUPPORT', 'AUDITOR'])
  const [editName, setEditName] = useState('')
  const [dialog, setDialog] = useState<Dialog>(null)
  const [saving, setSaving] = useState(false)
  // dialog fields
  const [editEmail, setEditEmail] = useState('')
  const [editRole, setEditRole] = useState('ADMIN')
  const [editPassword, setEditPassword] = useState('')
  const [creditRupees, setCreditRupees] = useState('1000')
  const [creditNote, setCreditNote] = useState('')
  const [activity, setActivity] = useState<ActivityItem[]>([])

  const loadStaff = useCallback(() => {
    setLoading(true)
    apiClient.get<StaffAdmin[]>('/admin/admins')
      .then(({ data }) => setStaff(data))
      .catch(() => showToast({ title: 'Staff directory unavailable', message: 'Administrator accounts could not be loaded.', type: 'error' }))
      .finally(() => setLoading(false))
  }, [])

  useEffect(loadStaff, [loadStaff])
  useEffect(() => {
    apiClient.get<Array<{ name: string }>>('/admin/roles')
      .then(({ data }) => setRoleNames(data.map((r) => r.name).filter((n) => n !== 'USER' && n !== 'SUPERADMIN')))
      .catch(() => undefined)
  }, [])

  const open = (next: Dialog) => {
    if (next?.kind === 'edit') {
      setEditName(next.user.full_name ?? '')
      setEditEmail(next.user.email ?? '')
      setEditRole(next.user.role ?? 'ADMIN')
      setEditPassword('')
    }
    if (next?.kind === 'credit') { setCreditRupees('1000'); setCreditNote('') }
    if (next?.kind === 'activity') {
      setActivity([])
      apiClient.get<{ items: ActivityItem[] }>(`/admin/admins/${next.user.id}/activity`, { params: { page_size: 50 } })
        .then(({ data }) => setActivity(data.items))
        .catch((error) => showToast({ title: 'Activity unavailable', message: getApiErrorMessage(error, 'Could not load activity.'), type: 'error' }))
    }
    setDialog(next)
  }
  const close = useCallback(() => setDialog(null), [])

  const run = async (fn: () => Promise<unknown>, success: string) => {
    setSaving(true)
    try {
      await fn()
      showToast({ title: success, message: 'Saved and recorded in the audit log.', type: 'success' })
      setDialog(null)
      loadStaff()
    } catch (error) {
      showToast({ title: 'Action failed', message: getApiErrorMessage(error, 'Please try again.'), type: 'error', duration: 7000 })
    } finally {
      setSaving(false)
    }
  }

  const toggleBlock = (user: StaffAdmin) => run(
    () => apiClient.patch(`/admin/admins/${user.id}/status`, { is_active: !user.is_active }),
    user.is_active ? `${user.username} blocked` : `${user.username} unblocked`,
  )

  const actionButton = (label: string, icon: React.ReactNode, onClick: () => void, tone = 'text-slate-300 hover:text-white') => (
    <button type="button" title={label} aria-label={label} onClick={onClick} className={`rounded-lg p-1.5 hover:bg-dark-elevated ${tone}`}>{icon}</button>
  )

  const columns: Column<StaffAdmin>[] = [
    { header: 'Name', accessor: (user) => <div><p className="font-bold text-white">{user.full_name || '—'}</p><p className="font-mono text-[11px] text-slate-400">@{user.username}</p></div> },
    { header: 'Email', accessor: (user) => user.email || '—' },
    { header: 'Role', accessor: (user) => <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-purple-400">{user.role || '—'}</span> },
    { header: 'Status', accessor: (user) => user.is_active ? <span className="text-emerald-400">Active</span> : <span className="text-rose-400">Blocked</span> },
    { header: '2FA', accessor: (user) => user.totp_enabled ? <span className="text-emerald-400">On</span> : <span className="text-slate-500">Off</span> },
    { header: 'Last Login', accessor: (user) => user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never' },
    {
      header: 'Actions',
      align: 'right',
      accessor: (user) => {
        if (!isSuper) return <span className="text-slate-500">—</span>
        const isSuperRow = user.role === 'SUPERADMIN'
        return (
          <div className="flex justify-end gap-0.5">
            {actionButton('Activity', <Activity className="h-4 w-4" />, () => open({ kind: 'activity', user }))}
            {actionButton('Add demo cash', <Coins className="h-4 w-4" />, () => open({ kind: 'credit', user }), 'text-amber-300 hover:text-amber-200')}
            {!isSuperRow && actionButton('Edit', <Pencil className="h-4 w-4" />, () => open({ kind: 'edit', user }))}
            {!isSuperRow && actionButton(user.is_active ? 'Block' : 'Unblock', user.is_active ? <Ban className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />, () => void toggleBlock(user), user.is_active ? 'text-orange-300 hover:text-orange-200' : 'text-emerald-400 hover:text-emerald-300')}
            {!isSuperRow && actionButton('Remove admin', <Trash2 className="h-4 w-4" />, () => open({ kind: 'remove', user }), 'text-rose-400 hover:text-rose-300')}
          </div>
        )
      },
    },
  ]

  const user = dialog?.user

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-white">Staff & Administrators</h1>
          <p className="text-xs text-slate-400">Create, edit, block or remove admins, see their activity and give demo credits for testing games.</p>
        </div>
        {isSuper && (
          <Button type="button" onClick={() => navigate('/admin/admin-users/new')} leftIcon={<UserPlus className="h-4 w-4" />}>Add new admin</Button>
        )}
      </div>


      {loading ? <p className="text-sm text-slate-400">Loading staff…</p> : staff.length
        ? <DataTable columns={columns} data={staff} keyExtractor={(row) => row.id} />
        : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No staff accounts found.</p>}

      {/* Edit */}
      <Modal open={dialog?.kind === 'edit'} title={`Edit ${user?.username ?? ''}`} onClose={close}>
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault()
          if (!user) return
          const body: Record<string, string> = {}
          if (editName !== (user.full_name ?? '')) body.full_name = editName
          if (editEmail !== (user.email ?? '')) body.email = editEmail
          if (editRole !== user.role) body.role = editRole
          if (editPassword) body.password = editPassword
          if (Object.keys(body).length === 0) { close(); return }
          void run(() => apiClient.patch(`/admin/admins/${user.id}`, body), `${user.username} updated`)
        }}>
          <Input label="Full name" value={editName} maxLength={100} onChange={(e) => setEditName(e.target.value)} />
          <Input label="Email" type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} />
          <label className="flex flex-col gap-2 text-xs font-semibold text-slate-300">Role
            <select value={editRole} onChange={(e) => setEditRole(e.target.value)} className="rounded-xl border border-dark-border bg-dark-elevated px-3.5 py-2.5 text-sm text-white">
              {(roleNames.includes(editRole) ? roleNames : [editRole, ...roleNames]).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <Input label="New password (optional)" type="password" autoComplete="new-password" value={editPassword} onChange={(e) => setEditPassword(e.target.value)} helperText="12+ chars with upper, lower, number and symbol. Signs the admin out everywhere." />
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={close}>Cancel</Button><Button type="submit" isLoading={saving}>Save changes</Button></div>
        </form>
      </Modal>

      {/* Demo credit */}
      <Modal open={dialog?.kind === 'credit'} title={`Add demo cash · ${user?.username ?? ''}`} onClose={close}>
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault()
          const amount = Number(creditRupees)
          if (!user || !Number.isFinite(amount) || amount <= 0) return
          void run(() => apiClient.post(`/admin/admins/${user.id}/demo-credit`, { amount_paise: rupeeToPaise(amount), note: creditNote || undefined }), `${formatPaiseToRupee(rupeeToPaise(amount))} demo credits added`)
        }}>
          <p className="text-xs text-slate-400">Virtual credits so this admin can test the games. Logged in the audit trail and shown in Credit Flow.</p>
          <div className="flex flex-wrap gap-2">
            {[500, 1000, 5000, 10000].map((v) => (
              <button key={v} type="button" onClick={() => setCreditRupees(String(v))} className={`rounded-lg px-3 py-1.5 text-xs font-bold ${creditRupees === String(v) ? 'bg-amber-500 text-dark-bg' : 'bg-dark-elevated text-slate-300'}`}>₹{v.toLocaleString()}</button>
            ))}
          </div>
          <Input label="Amount (₹)" type="number" min={1} value={creditRupees} onChange={(e) => setCreditRupees(e.target.value)} required />
          <Input label="Note (optional)" value={creditNote} maxLength={200} onChange={(e) => setCreditNote(e.target.value)} />
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={close}>Cancel</Button><Button type="submit" isLoading={saving} leftIcon={<Coins className="h-4 w-4" />}>Add credits</Button></div>
        </form>
      </Modal>

      {/* Remove */}
      <Modal open={dialog?.kind === 'remove'} title="Remove admin access" onClose={close}>
        <p className="text-sm text-slate-300"><b className="text-white">{user?.username}</b> will lose all admin access, be signed out everywhere and the account will be disabled. Their audit history is kept.</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
          <Button type="button" variant="danger" isLoading={saving} onClick={() => user && void run(() => apiClient.delete(`/admin/admins/${user.id}`), `${user.username} removed`)}>Remove admin</Button>
        </div>
      </Modal>

      {/* Activity */}
      <Modal open={dialog?.kind === 'activity'} title={`Activity · ${user?.username ?? ''}`} onClose={close} wide>
        {activity.length === 0 ? <p className="text-sm text-slate-400">No recorded actions yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400"><th className="py-2 pr-3">When</th><th className="py-2 pr-3">Action</th><th className="py-2 pr-3">Target</th><th className="py-2">IP</th></tr></thead>
              <tbody>
                {activity.map((a) => (
                  <tr key={a.id} className="border-t border-dark-border/60">
                    <td className="py-2 pr-3 whitespace-nowrap text-slate-400">{new Date(a.created_at).toLocaleString()}</td>
                    <td className="py-2 pr-3 font-bold text-white">{a.action}</td>
                    <td className="py-2 pr-3 text-slate-300">{a.target_type}{a.target_id ? ` · ${a.target_id.slice(0, 12)}` : ''}</td>
                    <td className="py-2 font-mono text-slate-400">{a.ip_address ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  )
}

export const AdminUsersStaff = AdminUsers
