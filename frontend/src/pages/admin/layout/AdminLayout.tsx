import React from 'react'
import { Outlet } from 'react-router-dom'
import { AdminHeader } from './AdminHeader'
import { AdminSidebar } from './AdminSidebar'
import { ToastContainer } from '../../../components/common/Toast'

export const AdminLayout: React.FC = () => {
  return (
    <div className="min-h-screen bg-dark-bg flex flex-col dark text-white">
      <AdminHeader />
      <div className="flex flex-1 overflow-hidden">
        <AdminSidebar />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <ToastContainer />
    </div>
  )
}

