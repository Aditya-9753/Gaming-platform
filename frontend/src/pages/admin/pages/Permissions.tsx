import React, { useEffect, useMemo, useState } from 'react'
import { Check, Key, Minus } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { getApiErrorMessage } from '../../../utils/apiError'
import { groupPermissions, type PermissionRow, type RoleRow } from './Roles'

/** Read-only matrix: which role holds which permission. Edit on the Roles page. */
export const Permissions: React.FC = () => {
  const [roles, setRoles] = useState<RoleRow[]>([])
  const [perms, setPerms] = useState<PermissionRow[]>([])

  useEffect(() => {
    Promise.all([apiClient.get<RoleRow[]>('/admin/roles'), apiClient.get<PermissionRow[]>('/admin/permissions')])
      .then(([r, p]) => { setRoles(r.data); setPerms(p.data) })
      .catch((error) => showToast({ title: 'Permissions unavailable', message: getApiErrorMessage(error, 'Only the super admin can view this.'), type: 'error' }))
  }, [])

  const grouped = useMemo(() => groupPermissions(perms), [perms])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Key className="h-6 w-6 text-purple-400" />
        <div>
          <h1 className="text-2xl font-black text-white">Permission Matrix</h1>
          <p className="text-xs text-slate-400">Which role can do what. Change assignments on the Roles page.</p>
        </div>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-dark-border bg-dark-card">
        <table className="w-full text-xs">
          <thead className="bg-dark-elevated text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Permission</th>
              {roles.map((r) => <th key={r.id} className="px-3 py-3 text-center font-black">{r.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {grouped.map(([group, items]) => (
              <React.Fragment key={group}>
                <tr><td colSpan={roles.length + 1} className="bg-dark-bg/60 px-4 py-1.5 text-[10px] font-black uppercase tracking-wider text-purple-300">{group}</td></tr>
                {items.map((p) => (
                  <tr key={p.code} className="border-t border-dark-border/50">
                    <td className="px-4 py-2"><span className="font-mono text-white">{p.code}</span> <span className="text-slate-500">— {p.description || p.name}</span></td>
                    {roles.map((r) => {
                      const has = r.name === 'SUPERADMIN' || r.permissions.includes(p.code)
                      return <td key={r.id} className="px-3 py-2 text-center">{has ? <Check className="mx-auto h-4 w-4 text-emerald-400" /> : <Minus className="mx-auto h-4 w-4 text-slate-600" />}</td>
                    })}
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
