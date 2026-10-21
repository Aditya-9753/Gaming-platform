export interface RoleRow { id: number; name: string; description: string | null; permissions: string[] }
export interface PermissionRow { id: number; code: string; name: string; description: string | null }

/** Group permission codes by their prefix ("wallet:read" -> "wallet"). */
export const groupPermissions = (perms: PermissionRow[]) => {
  const groups: Record<string, PermissionRow[]> = {}
  for (const p of perms) (groups[p.code.split(':')[0]] ??= []).push(p)
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
}
