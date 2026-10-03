import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  History,
  LayoutDashboard,
  Gamepad2,
  Plane,
  Palette,
  Bomb,
  Activity,
  Wallet,
  Trophy,
  Headphones,
  User,
  X,
  Spade,
  Gift,
  LogOut,
  Shield,
  Banknote,
} from 'lucide-react'
import { useUIStore } from '../../store/ui.store'
import { useAuthStore } from '../../store/auth.store'
import { authApi } from '../../services/auth.api'
import { isStaffRole } from '../../types/auth.types'

interface NavItem {
  name: string
  to: string
  icon: React.ReactNode
  badge?: string
  authRequired?: boolean
}

const navItems: NavItem[] = [
  { name: 'Dashboard', to: '/dashboard', icon: <LayoutDashboard className="w-5 h-5" />, authRequired: true },
  { name: 'Casino', to: '/games', icon: <Gamepad2 className="w-5 h-5" /> },
  { name: 'Aviator', to: '/games/aviator', icon: <Plane className="w-5 h-5" />, badge: 'LIVE' },
  { name: 'Teen Patti', to: '/games/teen-patti', icon: <Spade className="w-5 h-5" />, badge: 'NEW' },
  { name: 'Color Prediction', to: '/games/color', icon: <Palette className="w-5 h-5" />, badge: 'LIVE' },
  { name: 'Mines', to: '/games/mines', icon: <Bomb className="w-5 h-5" />, badge: 'LIVE' },
  { name: 'Sports', to: '/games/cricket', icon: <Activity className="w-5 h-5" />, badge: 'SOON' },
  { name: 'My Bets', to: '/history', icon: <History className="w-5 h-5" />, authRequired: true },
  { name: 'Deposit & Withdraw', to: '/payments', icon: <Banknote className="w-5 h-5" />, authRequired: true },
  { name: 'Wallet', to: '/wallet', icon: <Wallet className="w-5 h-5" />, authRequired: true },
  { name: 'Leaderboard', to: '/leaderboard', icon: <Trophy className="w-5 h-5" /> },
  { name: 'My Profile', to: '/profile', icon: <User className="w-5 h-5" />, authRequired: true },
]

const badgeTone: Record<string, string> = {
  LIVE: 'bg-green-600 text-white',
  NEW: 'bg-orange-500 text-white',
  SOON: 'bg-dark-elevated text-slate-400',
}

export const Sidebar: React.FC = () => {
  const { sidebarOpen, setSidebarOpen } = useUIStore()
  const { isAuthenticated, user, logout } = useAuthStore()
  const navigate = useNavigate()
  const close = () => setSidebarOpen(false)
  const handleLogout = async () => {
    close()
    try { await authApi.logout() } catch { /* local session is cleared anyway */ }
    logout()
    navigate('/login')
  }

  const filteredItems = navItems.filter((item) => !item.authRequired || isAuthenticated)

  return (
    <>
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div onClick={close} className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden" />
      )}

      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-50 lg:z-auto w-[82%] max-w-[320px] lg:w-64 bg-dark-card border-r border-dark-border flex flex-col transition-transform duration-300 lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Account header (drawer) */}
        <div className="p-4 border-b border-dark-border space-y-3">
          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Link to="/profile" onClick={close} className="flex min-w-0 flex-1 items-center gap-3">
                <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-dark-elevated text-lg font-black text-white">
                  {(user?.username || 'U')[0].toUpperCase()}
                  <span className="absolute right-0 top-0 h-2.5 w-2.5 rounded-full bg-orange-500 ring-2 ring-dark-card" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-base font-black text-white">{user?.username}</span>
                  <span className="block truncate text-xs text-slate-500">ID {user?.id?.slice(0, 8)}</span>
                </span>
                <ChevronRight className="ml-auto h-5 w-5 shrink-0 text-slate-500" />
              </Link>
            ) : (
              <div className="flex flex-1 gap-2">
                <Link to="/login" onClick={close} className="flex-1 rounded-xl bg-dark-elevated py-2.5 text-center text-sm font-bold text-white">Log in</Link>
                <Link to="/register" onClick={close} className="flex-1 rounded-xl bg-brand-blue py-2.5 text-center text-sm font-bold text-white">Sign up</Link>
              </div>
            )}
            <button onClick={close} aria-label="Close menu" className="rounded-full bg-dark-elevated p-1.5 text-slate-300 hover:text-white lg:hidden">
              <X className="h-5 w-5" />
            </button>
          </div>
          <Link
            to={isAuthenticated ? '/wallet' : '/register'}
            onClick={close}
            className="relative flex h-16 items-center overflow-hidden rounded-2xl bg-gradient-to-r from-emerald-900 via-emerald-800 to-emerald-600 px-4"
          >
            <span className="text-sm font-black leading-tight text-white">Free<br />bonus</span>
            <Gift aria-hidden className="absolute right-4 h-9 w-9 text-white/80" />
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
          {filteredItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/games'}
              onClick={close}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-3 rounded-xl text-sm font-semibold transition-all ${
                  isActive ? 'bg-brand-blue/15 text-white' : 'text-slate-300 hover:text-white hover:bg-dark-elevated'
                }`
              }
            >
              <span className="flex items-center gap-3.5 text-slate-200">
                <span className="text-slate-400">{item.icon}</span>
                <span>{item.name}</span>
              </span>
              {item.badge && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${badgeTone[item.badge] ?? ''}`}>{item.badge}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-dark-border space-y-2">
          {isAuthenticated && (
            <div className="flex gap-2 lg:hidden">
              {isStaffRole(user?.role) && (
                <Link to="/admin/dashboard" onClick={close} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-purple-500/15 py-2.5 text-xs font-bold text-purple-300">
                  <Shield className="h-4 w-4" />Admin
                </Link>
              )}
              <button type="button" onClick={() => void handleLogout()} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-dark-elevated py-2.5 text-xs font-bold text-rose-300">
                <LogOut className="h-4 w-4" />Log out
              </button>
            </div>
          )}
          <Link
            to={isAuthenticated ? '/support' : '/login'}
            onClick={close}
            className="flex items-center justify-between rounded-xl bg-dark-elevated px-3 py-3 text-sm font-semibold text-white"
          >
            <span className="flex items-center gap-3"><Headphones className="h-5 w-5 text-slate-400" />Support</span>
            <span className="rounded-full bg-brand-blue px-2 py-0.5 text-[10px] font-black">24/7</span>
          </Link>
        </div>
      </aside>
    </>
  )
}
