import React, { useEffect, useState } from 'react'
import { UserTable } from '../components/UserTable'
import { Input } from '../../../components/common/Input'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import type { AdminUserRecord } from '../../../types/admin.types'
import { STAFF_ROLES, type UserRole } from '../../../types/auth.types'

interface ApiUser {
  id: string
  username: string
  email: string | null
  role: string | null
  is_active: boolean
  balance: number
  created_at: string
}

interface UserResponse { items: ApiUser[]; total: number; total_pages: number }

export const Users: React.FC = () => {
  const [search, setSearch] = useState('')
  const [users, setUsers] = useState<AdminUserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  useEffect(() => { setPage(1) }, [search])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true)
      apiClient.get<UserResponse>('/admin/users', { params: { q: search || undefined, page, page_size: 50 } })
        .then(({ data }) => { setTotal(data.total); setTotalPages(data.total_pages); return data })
        .then((data) => setUsers(data.items.map((user) => ({
          id: user.id,
          username: user.username,
          phone: user.email || '—',
          email: user.email || '',
          role: (STAFF_ROLES as string[]).includes(user.role?.toLowerCase() ?? '')
            ? (user.role!.toLowerCase() as UserRole)
            : 'user',
          balancePaise: user.balance,
          status: user.is_active ? 'active' : 'suspended',
          createdAt: user.created_at,
        }))))
        .catch(() => showToast({ title: 'Users unavailable', message: 'Could not load users from the server.', type: 'error' }))
        .finally(() => setLoading(false))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search, page])

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-black text-white">Registered Users</h1>
          <p className="text-xs text-slate-400">{total} accounts on the platform • search and manage</p>
        </div>
        <div className="w-full sm:w-72">
          <Input placeholder="Search username, email, or ID..." value={search} onChange={(e) => setSearch(e.target.value)} leftElement={<Search className="h-4 w-4 text-slate-400" />} />
        </div>
      </div>
      {loading ? <p className="text-sm text-slate-400">Loading users…</p> : users.length ? <UserTable users={users} /> : <p className="rounded-xl border border-dark-border bg-dark-card p-5 text-sm text-slate-400">No users found.</p>}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm text-slate-400">
          <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-dark-border p-1.5 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
          <span>Page {page} of {totalPages}</span>
          <button type="button" aria-label="Next page" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-dark-border p-1.5 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
        </div>
      )}
    </div>
  )
}
