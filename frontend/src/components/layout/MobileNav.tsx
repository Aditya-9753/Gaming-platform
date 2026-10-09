import React from 'react'
import { NavLink } from 'react-router-dom'
import { Menu, Home, Spade, Gift, Trophy } from 'lucide-react'
import { useAuthStore } from '../../store/auth.store'
import { useUIStore } from '../../store/ui.store'
import { t as tr } from '../../i18n'

export const MobileNav: React.FC = () => {
  const { isAuthenticated } = useAuthStore()
  const { toggleSidebar, sidebarOpen } = useUIStore()

  const links = [
    { to: isAuthenticated ? '/dashboard' : '/', label: 'Home', icon: <Home className="w-5 h-5" /> },
    { to: '/games', label: 'Casino', icon: <Spade className="w-5 h-5" /> },
    { to: isAuthenticated ? '/wallet' : '/register', label: 'Free bonus', icon: <Gift className="w-5 h-5" /> },
    { to: '/games/cricket', label: 'Sports', icon: <Trophy className="w-5 h-5" /> },
  ]
  const item = 'flex flex-1 flex-col items-center gap-1 py-1 text-[10px] font-bold transition-colors'

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-dark-card/95 backdrop-blur-md border-t border-dark-border px-1 pt-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] flex items-center">
      <button type="button" onClick={toggleSidebar} className={`${item} ${sidebarOpen ? 'text-brand-blue' : 'text-slate-400'}`}>
        <Menu className="w-5 h-5" />
        <span>{tr('Menu')}</span>
      </button>
      {links.map((link) => (
        <NavLink
          key={link.label}
          to={link.to}
          end={link.to === '/games'}
          className={({ isActive }) => `${item} ${isActive ? 'text-brand-blue' : 'text-slate-400 hover:text-slate-200'}`}
        >
          {link.icon}
          <span>{tr(link.label)}</span>
        </NavLink>
      ))}
    </nav>
  )
}
