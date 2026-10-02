import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Save, Shield } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Button } from '../../../components/common/Button'
import { Input } from '../../../components/common/Input'
import { Modal } from '../components/Modal'
import { getApiErrorMessage } from '../../../utils/apiError'

export interface RoleRow { id: number; name: string; description: string | null; permissions: string[] }
export interface PermissionRow { id: number; code: string; name: string; description: string | null }

/** Group permission codes by their prefix ("wallet:read" -> "wallet"). */
export const groupPermissions = (perms: PermissionRow[]) => {
  const groups: Record<string, PermissionRow[]> = {}
  for (const p of perms) (groups[p.code.split(':')[0]] ??= []).push(p)
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
}

export const Roles: React.FC = () => {
  const [roles, setRoles] = useState<RoleRow[]>([])
  const [perms, setPerms] = useState<PermissionRow[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  const load = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([apiClient.get<RoleRow[]>('/admin/roles'), apiClient.get<PermissionRow[]>('/admin/permissions')])
      setRoles(r.data)
      setPerms(p.data)
      setSelectedId((id) => id ?? r.data[0]?.id ?? null)
    } catch (error) {
      showToast({ title: 'Roles unavailable', message: getApiErrorMessage(error, 'Only the super admin can manage roles.'), type: 'error' })
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const selected = roles.find((r) => r.id === selectedId) ?? null
  useEffect(() => { setDraft(new Set(selected?.permissions ?? [])) }, [selected])
  const grouped = useMemo(() => groupPermissions(perms), [perms])
  const locked = selected?.name === 'SUPERADMIN'
  const dirty = selected ? selected.permissions.length !== draft.size || selected.permissions.some((c) => !draft.has(c)) : false

  const toggle = (code: string) => setDraft((d) => {
    const next = new Set(d)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    return next
  })

  const save = async () => {
    if (!selected) return
    setSaving(true)
    try {
      await apiClient.put(`/admin/roles/${selected.id}/permissions`, { permission_codes: [...draft] })
      showToast({ title: 'Permissions saved', message: `${selected.name} updated (audit logged).`, type: 'success' })
      await load()
    } catch (error) {
      showToast({ title: 'Could not save', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const createRole = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const { data } = await apiClient.post<{ id: number }>('/admin/roles', { name: newName, description: newDesc, permission_codes: [] })
      showToast({ title: 'Role created', message: `${newName.toUpperCase()} — now tick its permissions.`, type: 'success' })
      setCreating(false); setNewName(''); setNewDesc('')
      await load()
      setSelectedId(data.id)
    } catch (error) {
      showToast({ title: 'Could not create role', message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Roles & Permissions</h1>
          <p className="text-xs text-slate-400">Create roles and choose exactly what each role can do. Every change is audit logged.</p>
        </div>
        <Button type="button" leftIcon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>New role</Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <div className="space-y-2">
          {roles.map((r) => (
            <button key={r.id} type="button" onClick={() => setSelectedId(r.id)} className={`w-full rounded-xl border p-3 text-left transition ${r.id === selectedId ? 'border-purple-500 bg-purple-500/10' : 'border-dark-border bg-dark-card hover:border-slate-600'}`}>
              <span className="flex items-center gap-2 text-sm font-black text-white"><Shield className="h-4 w-4 text-purple-400" />{r.name}</span>
              <span className="mt-1 block text-[11px] text-slate-400">{r.name === 'SUPERADMIN' ? 'All permissions (always)' : `${r.permissions.length} permissions`}</span>
            </button>
          ))}
        </div>

        {selected && (
          <div className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-white">{selected.name}</h2>
                <p className="text-xs text-slate-400">{selected.description}</p>
              </div>
              {!locked && <Button type="button" leftIcon={<Save className="h-4 w-4" />} disabled={!dirty} isLoading={saving} onClick={() => void save()}>Save permissions</Button>}
            </div>
            {locked && <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">The super admin always has every permission; it cannot be restricted.</p>}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {grouped.map(([group, items]) => (
                <div key={group} className="rounded-xl bg-dark-elevated p-3">
                  <p className="mb-2 text-[11px] font-black uppercase tracking-wider text-purple-300">{group}</p>
                  {items.map((p) => (
                    <label key={p.code} className="flex cursor-pointer items-start gap-2 py-1 text-xs text-slate-300">
                      <input type="checkbox" className="mt-0.5 rounded" disabled={locked} checked={locked || draft.has(p.code)} onChange={() => toggle(p.code)} />
                      <span><span className="font-mono text-white">{p.code}</span><br /><span className="text-slate-500">{p.description || p.name}</span></span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal open={creating} title="Create role" onClose={() => setCreating(false)}>
        <form className="space-y-4" onSubmit={(e) => void createRole(e)}>
          <Input label="Role name" value={newName} onChange={(e) => setNewName(e.target.value)} minLength={2} maxLength={50} helperText="e.g. GAME_OPERATOR" required />
          <Input label="Description" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} minLength={3} maxLength={200} required />
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" isLoading={saving}>Create</Button></div>
        </form>
      </Modal>
    </div>
  )
}
