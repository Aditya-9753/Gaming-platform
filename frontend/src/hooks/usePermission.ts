import { useAuthStore } from '../store/auth.store'
import { isStaffRole, type UserRole } from '../types/auth.types'

export function usePermission() {
  const { user } = useAuthStore()

  const hasRole = (role: UserRole): boolean => user?.role === role
  const isAdmin = (): boolean => user?.role === 'admin' || user?.role === 'superadmin'
  const isSuperAdmin = (): boolean => user?.role === 'superadmin'
  const isStaff = (): boolean => isStaffRole(user?.role)
  const isAuthenticated = (): boolean => Boolean(user)
  /** Mirrors the backend RBAC check: super admin always passes. */
  const hasPermission = (code: string): boolean => user?.role === 'superadmin' || Boolean(user?.permissions.includes(code))

  return { hasRole, isAdmin, isSuperAdmin, isStaff, isAuthenticated, hasPermission }
}
