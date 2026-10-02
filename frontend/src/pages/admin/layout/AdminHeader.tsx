import React from 'react'
import { Link } from 'react-router-dom'
import { Shield, ArrowLeft, LogOut } from 'lucide-react'
import { useAuthStore } from '../../../store/auth.store'

export const AdminHeader: React.FC = () => {
  const { user, logout } = useAuthStore()

  return (
    <header className="h-16 bg-dark-card border-b border-dark-border px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Link
          to="/dashboard"
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Exit to Player App</span>
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center font-black text-xs">
            <Shield className="w-4 h-4" />
          </div>
          <div className="text-left hidden sm:block">
            <span className="text-xs font-bold text-white block">{user?.username || 'Admin'}</span>
            <span className="text-[10px] text-purple-400 font-semibold block uppercase">
              {user?.role || 'Super Admin'}
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

