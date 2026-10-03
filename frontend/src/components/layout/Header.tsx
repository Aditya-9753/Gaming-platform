import React, { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Wallet, Menu, LogOut, Shield } from 'lucide-react'
import { BrandLogo } from '../common/BrandLogo'
import { useAuthStore } from '../../store/auth.store'
import { useWalletStore } from '../../store/wallet.store'
import { useUIStore } from '../../store/ui.store'
import { formatPaiseToRupee } from '../../utils/formatters'
import { Button } from '../common/Button'
import { LanguageSwitcher } from '../common/LanguageSwitcher'
import { NotificationBell } from '../notifications/NotificationBell'
import { walletApi } from '../../services/wallet.api'
import { authApi } from '../../services/auth.api'
import { showToast } from '../common/Toast'
import { isStaffRole } from '../../types/auth.types'

export const Header: React.FC = () => {
  const navigate = useNavigate()
  const { user, isAuthenticated, logout } = useAuthStore()
  const { balance } = useWalletStore()
  const { toggleSidebar } = useUIStore()

  useEffect(() => {
    if (isAuthenticated) {
      walletApi.getBalance().then((value) => useWalletStore.getState().setBalance(value)).catch(() => {
        showToast({ title: 'Wallet unavailable', message: 'Your server balance could not be loaded.', type: 'warning' })
      })
    }
  }, [isAuthenticated])

  const handleLogout = async () => {
    try {
      await authApi.logout()
    } catch {
      showToast({ title: 'Logout warning', message: 'The server session could not be revoked; local access was cleared.', type: 'warning' })
    } finally {
      logout()
      navigate('/login')
    }
  }

  return (
    <header className="sticky top-0 z-40 h-16 bg-[#101012]/95 backdrop-blur-md border-b border-dark-border px-3 sm:px-6 flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
        <button
          onClick={toggleSidebar}
          aria-label="Open menu"
          className="hidden p-2 text-slate-400 hover:text-white rounded-xl hover:bg-dark-elevated transition-colors"
        >
          <Menu className="w-5 h-5" />
        </button>

        <Link to="/" className="flex items-center gap-2">
          <BrandLogo
            iconClassName="hidden sm:flex w-8 h-8 rounded-lg bg-gradient-to-tr from-orange-500 to-amber-400 text-white"
            textClassName="text-xl sm:text-2xl font-black italic tracking-tight text-white"
          />
        </Link>
      </div>

      <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
        <div className="hidden sm:block"><LanguageSwitcher /></div>

        {isAuthenticated ? (
          <>
            {/* Balance + wallet button */}
            <Link to="/wallet" className="text-right leading-tight">
              <span className="block text-[10px] font-bold text-slate-400">INR</span>
              <span className="block text-sm font-black text-white">{formatPaiseToRupee(balance.realBalancePaise)}</span>
            </Link>
            <Link
              to="/wallet"
              className="flex items-center gap-1.5 rounded-xl bg-brand-green px-3 sm:px-4 py-2 text-xs sm:text-sm font-black text-white shadow-md hover:brightness-110"
            >
              <Wallet className="hidden sm:block w-4 h-4" />
              Wallet
            </Link>

            <NotificationBell />

            {/* User Dropdown / Admin Link (desktop; phones use the Menu drawer) */}
            <div className="hidden lg:flex items-center gap-1 sm:gap-2">
              {isStaffRole(user?.role) && (
                <Link
                  to="/admin/dashboard"
                  className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-bold hover:bg-purple-500/20 transition-all"
                >
                  <Shield className="w-3.5 h-3.5" />
                  <span>Admin</span>
                </Link>
              )}

              <Link
                to="/profile"
                className="w-8 h-8 sm:w-9 sm:h-9 shrink-0 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center font-bold text-dark-bg text-sm shadow-md"
              >
                {(user?.username || 'U')[0].toUpperCase()}
              </Link>

              <button
                onClick={() => void handleLogout()}
                title="Logout"
                aria-label="Logout"
                className="p-1.5 sm:p-2 text-slate-400 hover:text-rose-400 rounded-xl hover:bg-dark-elevated transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>
              Log In
            </Button>
            <Button variant="primary" size="sm" onClick={() => navigate('/register')}>
              Sign Up
            </Button>
          </div>
        )}
      </div>
    </header>
  )
}
