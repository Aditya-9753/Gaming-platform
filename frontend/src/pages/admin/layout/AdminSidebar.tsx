import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Gamepad2,
  Sliders,
  Radio,
  History,
  Receipt,
  Wallet,
  Coins,
  BarChart3,
  Bell,
  Headphones,
  UserCheck,
  Shield,
  Key,
  FileText,
  Lock,
  Settings,
  Landmark,
  UserPlus,
  ShieldCheck,
} from 'lucide-react'
import { useAuthStore } from '../../../store/auth.store'
import { usePermission } from '../../../hooks/usePermission'

const adminLinks = [
  { name: 'Dashboard', to: '/admin/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
  { name: 'User Management', to: '/admin/users', icon: <Users className="w-4 h-4" />, perm: 'user:read' },
  { name: 'Game Catalog', to: '/admin/games', icon: <Gamepad2 className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Game Settings', to: '/admin/game-settings', icon: <Sliders className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Exposure Monitor', to: '/admin/live-games', icon: <Radio className="w-4 h-4" />, superOnly: true },
  { name: 'Provably Fair', to: '/admin/fairness', icon: <ShieldCheck className="w-4 h-4" />, superOnly: true },
  { name: 'Game Rounds', to: '/admin/rounds', icon: <History className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Transactions', to: '/admin/transactions', icon: <Receipt className="w-4 h-4" />, perm: 'ledger:read' },
  { name: 'Vault & Wallets', to: '/admin/wallets', icon: <Wallet className="w-4 h-4" />, perm: 'ledger:read' },
  { name: 'Manual Adjustment', to: '/admin/wallet-adjustment', icon: <Coins className="w-4 h-4" />, perm: 'wallet:adjust' },
  { name: 'Credit Flow', to: '/admin/credit-flow', icon: <Landmark className="w-4 h-4" />, superOnly: true },
  { name: 'Reports & Analytics', to: '/admin/reports', icon: <BarChart3 className="w-4 h-4" />, perm: 'report:export' },
  { name: 'Broadcast Alerts', to: '/admin/notifications', icon: <Bell className="w-4 h-4" />, perm: 'notification:manage' },
  { name: 'Support Tickets', to: '/admin/support', icon: <Headphones className="w-4 h-4" />, perm: 'ticket:manage' },
  { name: 'Staff Admins', to: '/admin/admin-users', icon: <UserCheck className="w-4 h-4" />, superOnly: true },
  { name: 'Add New Admin', to: '/admin/admin-users/new', icon: <UserPlus className="w-4 h-4" />, superOnly: true },
  { name: 'Roles (RBAC)', to: '/admin/roles', icon: <Shield className="w-4 h-4" />, superOnly: true },
  { name: 'Permissions', to: '/admin/permissions', icon: <Key className="w-4 h-4" />, superOnly: true },
  { name: 'Audit Logs', to: '/admin/audit-logs', icon: <FileText className="w-4 h-4" />, perm: 'audit:read' },
  { name: 'Email 2FA', to: '/admin/2fa', icon: <Lock className="w-4 h-4" /> },
  { name: 'Platform Settings', to: '/admin/settings', icon: <Settings className="w-4 h-4" />, superOnly: true },
]

export const AdminSidebar: React.FC = () => {
  const isSuper = useAuthStore((s) => s.user?.role === 'superadmin')
  const { hasPermission } = usePermission()
  // UI convenience only — every page's API enforces the same rules server-side
  const links = (adminLinks as Array<{ name: string; to: string; icon: React.ReactNode; superOnly?: boolean; perm?: string }>)
    .filter((l) => (l.superOnly ? isSuper : !l.perm || hasPermission(l.perm)))
  return (
    <aside className="w-64 bg-dark-card border-r border-dark-border flex flex-col h-full shrink-0">
      <div className="h-16 flex items-center px-6 border-b border-dark-border">
        <span className="text-sm font-black tracking-wider text-purple-400">
          ADMIN CONTROL
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto p-4 space-y-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                isActive
                  ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                  : 'text-slate-400 hover:text-white hover:bg-dark-elevated'
              }`
            }
          >
            {link.icon}
            <span>{link.name}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

