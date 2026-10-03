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
  Fingerprint,
  Gauge,
  Banknote,
  X,
} from 'lucide-react'
import { useAuthStore } from '../../../store/auth.store'
import { usePermission } from '../../../hooks/usePermission'

const adminLinks = [
  { name: 'Dashboard', to: '/admin/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
  { name: 'User Management', to: '/admin/users', icon: <Users className="w-4 h-4" />, perm: 'user:read' },
  { name: 'Game Catalog', to: '/admin/games', icon: <Gamepad2 className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Game Settings', to: '/admin/game-settings', icon: <Sliders className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Exposure Monitor', to: '/admin/live-games', icon: <Radio className="w-4 h-4" />, superOnly: true },
  { name: 'Risk Controls', to: '/admin/risk-controls', icon: <Gauge className="w-4 h-4" />, superOnly: true },
  { name: 'Provably Fair', to: '/admin/fairness', icon: <ShieldCheck className="w-4 h-4" />, superOnly: true },
  { name: 'Game Rounds', to: '/admin/rounds', icon: <History className="w-4 h-4" />, perm: 'game:manage' },
  { name: 'Payments', to: '/admin/payments', icon: <Banknote className="w-4 h-4" />, perm: 'payment:read' },
  { name: 'Transactions', to: '/admin/transactions', icon: <Receipt className="w-4 h-4" />, perm: 'ledger:read' },
  { name: 'Vault & Wallets', to: '/admin/wallets', icon: <Wallet className="w-4 h-4" />, perm: 'ledger:read' },
  { name: 'Manual Adjustment', to: '/admin/wallet-adjustment', icon: <Coins className="w-4 h-4" />, perm: 'wallet:adjust' },
  { name: 'Credit Flow', to: '/admin/credit-flow', icon: <Landmark className="w-4 h-4" />, superOnly: true },
  { name: 'Security & Fairness', to: '/admin/security', icon: <Fingerprint className="w-4 h-4" />, superOnly: true },
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

interface AdminSidebarProps {
  /** Phones/tablets: the drawer is shown. Ignored on desktop, where the sidebar is always visible. */
  open: boolean
  onClose: () => void
}

export const AdminSidebar: React.FC<AdminSidebarProps> = ({ open, onClose }) => {
  const isSuper = useAuthStore((s) => s.user?.role === 'superadmin')
  const { hasPermission } = usePermission()
  // UI convenience only — every page's API enforces the same rules server-side
  const links = (adminLinks as Array<{ name: string; to: string; icon: React.ReactNode; superOnly?: boolean; perm?: string }>)
    .filter((l) => (l.superOnly ? isSuper : !l.perm || hasPermission(l.perm)))
  return (
    <>
      {/* Backdrop behind the mobile drawer */}
      <div
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity lg:hidden ${open ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-dark-border bg-dark-card transition-transform duration-200 lg:static lg:z-auto lg:w-64 lg:max-w-none lg:shrink-0 lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Admin navigation"
      >
        <div className="flex h-14 items-center justify-between border-b border-dark-border px-5 lg:h-16 lg:px-6">
          <span className="text-sm font-black tracking-wider text-purple-400">ADMIN CONTROL</span>
          <button type="button" onClick={onClose} aria-label="Close menu" className="rounded-lg p-1.5 text-slate-400 hover:bg-dark-elevated hover:text-white lg:hidden">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3 lg:p-4">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-bold transition-all lg:py-2.5 lg:text-xs ${
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
    </>
  )
}
