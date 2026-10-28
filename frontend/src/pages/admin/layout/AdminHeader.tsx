import React from 'react'
import { Link } from 'react-router-dom'
import { Shield, ArrowLeft, LogOut, Menu } from 'lucide-react'
import { useAuthStore } from '../../../store/auth.store'

export const AdminHeader: React.FC<{ onMenu: () => void }> = ({ onMenu }) => {
  const { user, logout } = useAuthStore()
  const isSuper = user?.role === 'superadmin'

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-dark-border bg-dark-card px-3 sm:px-6 lg:h-16">
      <div className="flex items-center gap-2 sm:gap-3">
        <button type="button" onClick={onMenu} aria-label="Open admin menu" className="rounded-lg p-2 text-slate-300 hover:bg-dark-elevated hover:text-white lg:hidden">
          <Menu className="h-5 w-5" />
        </button>
        <Link
          to="/dashboard"
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="hidden sm:inline">Exit to Player App</span>
          <span className="sm:hidden">Exit</span>
        </Link>
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        <div className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-black text-xs ${isSuper ? 'bg-amber-500/15 text-amber-300' : 'bg-sky-500/15 text-sky-300'}`}>
            <Shield className="w-4 h-4" />
          </div>
          <div className="text-left hidden sm:block">
            <span className="text-xs font-bold text-white block">{user?.username || 'Admin'}</span>
            <span className={`text-[10px] font-semibold block uppercase ${isSuper ? 'text-amber-300' : 'text-sky-300'}`}>
              {isSuper ? 'Super Admin' : user?.role === 'admin' ? 'Admin' : user?.role || 'Staff'}
            </span>
          </div>
        </div>

        <button
          onClick={logout}
          title="Sign Out"
          className="p-2 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-dark-elevated transition-colors"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  )
}

