import React from 'react'
import { useAuthStore } from '../../../store/auth.store'
import type { UserRole } from '../../../types/auth.types'

export interface PermissionGateProps {
  roles?: UserRole[]
  children: React.ReactNode
  fallback?: React.ReactNode
}

export const PermissionGate: React.FC<PermissionGateProps> = ({
  roles = ['admin', 'superadmin'],
  children,
  fallback = null,
}) => {
  const { user } = useAuthStore()

  if (!user || !roles.includes(user.role)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}
