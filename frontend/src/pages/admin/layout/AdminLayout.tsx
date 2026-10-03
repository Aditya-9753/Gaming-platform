import React, { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AdminHeader } from './AdminHeader'
import { AdminSidebar } from './AdminSidebar'
import { ToastContainer } from '../../../components/common/Toast'

export const AdminLayout: React.FC = () => {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()

  // Close the mobile drawer on navigation and on Escape
  useEffect(() => { setMenuOpen(false) }, [pathname])
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="dark flex h-[100dvh] flex-col bg-dark-bg text-white">
      <AdminHeader onMenu={() => setMenuOpen(true)} />
      <div className="flex min-h-0 flex-1">
        <AdminSidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
        <main className="admin-main min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-5 lg:p-6">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
      <ToastContainer />
    </div>
  )
}
