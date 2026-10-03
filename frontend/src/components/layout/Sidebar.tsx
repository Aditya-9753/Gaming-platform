import React from 'react'
import { NavLink } from 'react-router-dom'
import {
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
} from 'lucide-react'
import { useUIStore } from '../../store/ui.store'
import { useAuthStore } from '../../store/auth.store'

interface NavItem {
  name: string
  to: string
  icon: React.ReactNode
  badge?: string
  authRequired?: boolean
}

const navItems: NavItem[] = [
  { name: 'Dashboard', to: '/dashboard', icon: <LayoutDashboard className="w-4 h-4" />, authRequired: true },
  { name: 'All Games', to: '/games', icon: <Gamepad2 className="w-4 h-4" /> },
  { name: 'Aviator', to: '/games/aviator', icon: <Plane className="w-4 h-4" /> },
  { name: 'Color Prediction', to: '/games/color', icon: <Palette className="w-4 h-4" /> },
  { name: 'Mines', to: '/games/mines', icon: <Bomb className="w-4 h-4" /> },
  { name: 'Cricket Live', to: '/games/cricket', icon: <Activity className="w-4 h-4" />, badge: 'SOON' },
  { name: 'My Bets', to: '/history', icon: <History className="w-4 h-4" />, authRequired: true },
  { name: 'Wallet', to: '/wallet', icon: <Wallet className="w-4 h-4" />, authRequired: true },
  { name: 'Leaderboard', to: '/leaderboard', icon: <Trophy className="w-4 h-4" /> },
  { name: 'Support', to: '/support', icon: <Headphones className="w-4 h-4" />, authRequired: true },
  { name: 'My Profile', to: '/profile', icon: <User className="w-4 h-4" />, authRequired: true },
]

export const Sidebar: React.FC = () => {
  const { sidebarOpen, setSidebarOpen } = useUIStore()
  const { isAuthenticated } = useAuthStore()

  const filteredItems = navItems.filter((item) => !item.authRequired || isAuthenticated)

  return (
    <>
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-40 w-64 bg-dark-card border-r border-dark-border flex flex-col transition-transform duration-300 lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-16 flex items-center justify-between px-6 border-b border-dark-border lg:hidden">
          <span className="text-sm font-black text-white">NAVIGATION</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-dark-elevated"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-1">
          {filteredItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-dark-elevated'
                }`
              }
            >
              <div className="flex items-center gap-3">
                {item.icon}
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-black bg-emerald-500 text-dark-bg">
                  {item.badge}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  )
}
