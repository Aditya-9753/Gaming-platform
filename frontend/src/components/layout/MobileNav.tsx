import React from 'react'
import { NavLink } from 'react-router-dom'
import { Home, Gamepad2, Wallet, Trophy, User } from 'lucide-react'
import { useAuthStore } from '../../store/auth.store'

export const MobileNav: React.FC = () => {
  const { isAuthenticated } = useAuthStore()

  const links = [
    { to: isAuthenticated ? '/dashboard' : '/', label: 'Home', icon: <Home className="w-5 h-5" /> },
    { to: '/games', label: 'Games', icon: <Gamepad2 className="w-5 h-5" /> },
    { to: '/wallet', label: 'Wallet', icon: <Wallet className="w-5 h-5" /> },
    { to: '/leaderboard', label: 'Top', icon: <Trophy className="w-5 h-5" /> },
    { to: isAuthenticated ? '/profile' : '/login', label: 'Account', icon: <User className="w-5 h-5" /> },
  ]

  return (
    <div className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-dark-card/95 backdrop-blur-md border-t border-dark-border py-2 px-4 flex items-center justify-around">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 text-[10px] font-bold transition-colors ${
              isActive ? 'text-emerald-400' : 'text-slate-400 hover:text-slate-200'
            }`
          }
        >
          {link.icon}
          <span>{link.label}</span>
        </NavLink>
      ))}
    </div>
  )
}

