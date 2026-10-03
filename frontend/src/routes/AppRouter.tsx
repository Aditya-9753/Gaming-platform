import React, { lazy, Suspense, useEffect } from 'react'
import {
  createBrowserRouter,
  RouterProvider,
  Outlet,
  Navigate,
  useLocation,
  Link,
} from 'react-router-dom'
import { Header } from '../components/layout/Header'
import { Sidebar } from '../components/layout/Sidebar'
import { Footer } from '../components/layout/Footer'
import { MobileNav } from '../components/layout/MobileNav'
import { MaintenanceBanner } from '../components/games/MaintenanceBanner'
import { AgeGateModal } from '../components/common/AgeGateModal'
import { ToastContainer } from '../components/common/Toast'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { Loader } from '../components/common/Loader'
import { useAuthStore } from '../store/auth.store'
import { authApi } from '../services/auth.api'
import { isStaffRole } from '../types/auth.types'

// Lazy-loaded routes
const Home = lazy(() => import('../pages/public/Home').then((m) => ({ default: m.Home })))
const Login = lazy(() => import('../pages/public/Login').then((m) => ({ default: m.Login })))
const Register = lazy(() => import('../pages/public/Register').then((m) => ({ default: m.Register })))
const ForgotPassword = lazy(() => import('../pages/public/ForgotPassword').then((m) => ({ default: m.ForgotPassword })))
const ResetPassword = lazy(() => import('../pages/public/ResetPassword').then((m) => ({ default: m.ResetPassword })))
const Terms = lazy(() => import('../pages/public/Terms').then((m) => ({ default: m.Terms })))
const Privacy = lazy(() => import('../pages/public/Privacy').then((m) => ({ default: m.Privacy })))
const NotFound = lazy(() => import('../pages/public/NotFound').then((m) => ({ default: m.NotFound })))

const Dashboard = lazy(() => import('../pages/user/Dashboard').then((m) => ({ default: m.Dashboard })))
const Games = lazy(() => import('../pages/user/Games').then((m) => ({ default: m.Games })))
const WalletPage = lazy(() => import('../pages/user/Wallet').then((m) => ({ default: m.WalletPage })))
const Profile = lazy(() => import('../pages/user/Profile').then((m) => ({ default: m.Profile })))
const Leaderboard = lazy(() => import('../pages/user/Leaderboard').then((m) => ({ default: m.Leaderboard })))
const FairnessPage = lazy(() => import('../pages/user/Fairness').then((m) => ({ default: m.FairnessPage })))
const BetHistory = lazy(() => import('../pages/user/BetHistory').then((m) => ({ default: m.BetHistory })))
const Support = lazy(() => import('../pages/user/Support').then((m) => ({ default: m.Support })))

const Aviator = lazy(() => import('../pages/games/Aviator/Aviator').then((m) => ({ default: m.Aviator })))
const WinGo = lazy(() => import('../pages/games/WinGo/WinGo').then((m) => ({ default: m.WinGo })))
const Mines = lazy(() => import('../pages/games/Mines/Mines').then((m) => ({ default: m.Mines })))
const TeenPatti = lazy(() => import('../pages/games/TeenPatti/TeenPatti').then((m) => ({ default: m.TeenPatti })))

const AdminLayout = lazy(() => import('../pages/admin/layout/AdminLayout').then((m) => ({ default: m.AdminLayout })))
const AdminDashboard = lazy(() => import('../pages/admin/pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const AdminUsers = lazy(() => import('../pages/admin/pages/Users').then((m) => ({ default: m.Users })))
const UserDetails = lazy(() => import('../pages/admin/pages/UserDetails').then((m) => ({ default: m.UserDetails })))
const AdminGames = lazy(() => import('../pages/admin/pages/Games').then((m) => ({ default: m.Games })))
const GameSettings = lazy(() => import('../pages/admin/pages/GameSettings').then((m) => ({ default: m.GameSettings })))
const LiveGames = lazy(() => import('../pages/admin/pages/LiveGames').then((m) => ({ default: m.LiveGames })))
const GameRounds = lazy(() => import('../pages/admin/pages/GameRounds').then((m) => ({ default: m.GameRounds })))
const AdminTransactions = lazy(() => import('../pages/admin/pages/Transactions').then((m) => ({ default: m.Transactions })))
const AdminWallet = lazy(() => import('../pages/admin/pages/Wallet').then((m) => ({ default: m.WalletPage })))
const WalletAdjustment = lazy(() => import('../pages/admin/pages/WalletAdjustment').then((m) => ({ default: m.WalletAdjustment })))
const AdminReports = lazy(() => import('../pages/admin/pages/Reports').then((m) => ({ default: m.Reports })))
const AdminNotifications = lazy(() => import('../pages/admin/pages/Notifications').then((m) => ({ default: m.AdminNotifications })))
const AdminSupport = lazy(() => import('../pages/admin/pages/Support').then((m) => ({ default: m.AdminSupport })))
const AdminUsersStaff = lazy(() => import('../pages/admin/pages/AdminUsers').then((m) => ({ default: m.AdminUsers })))
const Roles = lazy(() => import('../pages/admin/pages/Roles').then((m) => ({ default: m.Roles })))
const Permissions = lazy(() => import('../pages/admin/pages/Permissions').then((m) => ({ default: m.Permissions })))
const AuditLogs = lazy(() => import('../pages/admin/pages/AuditLogs').then((m) => ({ default: m.AuditLogs })))
const AddAdmin = lazy(() => import('../pages/admin/pages/AddAdmin').then((m) => ({ default: m.AddAdmin })))
const CreditFlow = lazy(() => import('../pages/admin/pages/CreditFlow').then((m) => ({ default: m.CreditFlow })))
const SecurityCenter = lazy(() => import('../pages/admin/pages/SecurityCenter').then((m) => ({ default: m.SecurityCenter })))
const Setup2FA = lazy(() => import('../pages/admin/pages/Setup2FA').then((m) => ({ default: m.Setup2FA })))
const AdminSettings = lazy(() => import('../pages/admin/pages/Settings').then((m) => ({ default: m.AdminSettings })))

/** Cricket is not open yet; its page stays in the codebase for later. */
const CricketComingSoon: React.FC = () => (
  <div className="max-w-md mx-auto mt-10 p-8 rounded-2xl bg-dark-card border border-blue-500/30 text-center space-y-3">
    <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">Coming Soon</span>
    <h2 className="text-2xl font-black text-white">Sports</h2>
    <p className="text-sm text-slate-400">Sports betting is launching soon. Meanwhile, try Teen Patti, Aviator, Mines or Color Prediction.</p>
    <Link to="/games/teen-patti" className="inline-block px-5 py-2.5 rounded-xl bg-brand-blue hover:brightness-110 text-white font-extrabold text-xs">Play Teen Patti</Link>
  </div>
)

// -------------------------------------------------------------------
// Route Guard Components
// -------------------------------------------------------------------

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuthStore()
  if (isLoading) return <Loader fullScreen />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

const RequireAdmin: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading } = useAuthStore()
  const location = useLocation()
  if (isLoading) return <Loader fullScreen />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!user || !isStaffRole(user.role)) {
    return <Navigate to="/dashboard" replace />
  }
  if (user.requires2FASetup && location.pathname !== '/admin/2fa') {
    return <Navigate to="/admin/2fa" replace />
  }
  return <>{children}</>
}

/** Super-admin-only pages. The matching APIs enforce the same rule server-side. */
const RequireSuperAdmin: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuthStore()
  if (user?.role !== 'superadmin') return <Navigate to="/admin/dashboard" replace />
  return <>{children}</>
}

const RedirectIfAuthed: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, user } = useAuthStore()
  // Admins that still must enrol 2FA go straight to the setup page
  if (isAuthenticated) return <Navigate to={user?.requires2FASetup ? '/admin/2fa' : '/dashboard'} replace />
  return <>{children}</>
}

/** Restore the session from the refresh cookie once, for every route (incl. /admin). */
function useSessionBootstrap() {
  const { setAuth, setLoading, logout } = useAuthStore()

  useEffect(() => {
    let active = true
    authApi.refreshToken()
      .then(async (tokens) => {
        if (!tokens?.access_token) {
          if (active) logout()
          return
        }
        const { access_token } = tokens
        useAuthStore.getState().setAccessToken(access_token)
        const user = await authApi.getCurrentUser()
        if (active) setAuth(user, access_token)
      })
      .catch(() => {
        if (active) logout()
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [logout, setAuth, setLoading])
}

// -------------------------------------------------------------------
// Main App Layout Shell
// -------------------------------------------------------------------

/** A single game page (not the /games lobby): keeps the original game colours. */
const GAME_PAGE = /^\/games\/(aviator|color|mines|teen-patti|cricket)(\/|$)/

const AppShell: React.FC = () => {
  // The site uses the navy + blue theme; game pages keep their own look (see .game-theme in index.css)
  const isGamePage = GAME_PAGE.test(useLocation().pathname)
  return <div className="min-h-screen bg-dark-bg flex flex-col dark">
    <AgeGateModal />
    <MaintenanceBanner />
    <Header />
    <div className="flex flex-1 overflow-hidden">
      <Sidebar />
      <main className={`flex-1 overflow-y-auto p-4 sm:p-6 pb-20 md:pb-6 ${isGamePage ? 'game-theme bg-dark-bg' : ''}`}>
        <div className="max-w-7xl mx-auto">
          <ErrorBoundary>
            <Suspense fallback={<Loader text="Loading..." />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
    </div>
    <Footer />
    <MobileNav />
    <ToastContainer />
  </div>
}

// -------------------------------------------------------------------
// Router Configuration
// -------------------------------------------------------------------

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      // Public Routes
      { path: '/', element: <Home /> },
      {
        path: '/login',
        element: (
          <RedirectIfAuthed>
            <Login />
          </RedirectIfAuthed>
        ),
      },
      {
        path: '/register',
        element: (
          <RedirectIfAuthed>
            <Register />
          </RedirectIfAuthed>
        ),
      },
      { path: '/forgot-password', element: <ForgotPassword /> },
      { path: '/reset-password', element: <ResetPassword /> },
      { path: '/terms', element: <Terms /> },
      { path: '/privacy', element: <Privacy /> },
      { path: '/leaderboard', element: <Leaderboard /> },

      // Authenticated User Routes
      {
        path: '/dashboard',
        element: (
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        ),
      },
      { path: '/games', element: <Games /> },
      { path: '/games/aviator', element: <RequireAuth><Aviator /></RequireAuth> },
      { path: '/games/color', element: <WinGo /> },
      { path: '/games/mines', element: <RequireAuth><Mines /></RequireAuth> },
      { path: '/games/teen-patti', element: <RequireAuth><TeenPatti /></RequireAuth> },
      { path: '/games/cricket', element: <CricketComingSoon /> },
      {
        path: '/wallet',
        element: (
          <RequireAuth>
            <WalletPage />
          </RequireAuth>
        ),
      },
      {
        path: '/profile',
        element: (
          <RequireAuth>
            <Profile />
          </RequireAuth>
        ),
      },
      { path: '/history', element: <RequireAuth><BetHistory /></RequireAuth> },
      { path: '/support', element: <RequireAuth><Support /></RequireAuth> },
      { path: '*', element: <NotFound /> },
    ],
  },

  // Admin Panel (Separate Layout)
  {
    path: '/admin',
    element: (
      <RequireAdmin>
        <Suspense fallback={<Loader fullScreen text="Loading Admin Panel..." />}>
          <AdminLayout />
        </Suspense>
      </RequireAdmin>
    ),
    children: [
      { index: true, element: <Navigate to="/admin/dashboard" replace /> },
      { path: 'dashboard', element: <AdminDashboard /> },
      { path: 'users', element: <AdminUsers /> },
      { path: 'users/:id', element: <UserDetails /> },
      { path: 'games', element: <AdminGames /> },
      { path: 'game-settings', element: <GameSettings /> },
      { path: 'live-games', element: <RequireSuperAdmin><LiveGames /></RequireSuperAdmin> },
      { path: 'fairness', element: <RequireSuperAdmin><FairnessPage /></RequireSuperAdmin> },
      { path: 'rounds', element: <GameRounds /> },
      { path: 'transactions', element: <AdminTransactions /> },
      { path: 'wallets', element: <AdminWallet /> },
      { path: 'wallet-adjustment', element: <WalletAdjustment /> },
      { path: 'reports', element: <AdminReports /> },
      { path: 'credit-flow', element: <RequireSuperAdmin><CreditFlow /></RequireSuperAdmin> },
      { path: 'security', element: <RequireSuperAdmin><SecurityCenter /></RequireSuperAdmin> },
      { path: 'notifications', element: <AdminNotifications /> },
      { path: 'support', element: <AdminSupport /> },
      { path: 'admin-users', element: <RequireSuperAdmin><AdminUsersStaff /></RequireSuperAdmin> },
      { path: 'admin-users/new', element: <RequireSuperAdmin><AddAdmin /></RequireSuperAdmin> },
      { path: 'roles', element: <RequireSuperAdmin><Roles /></RequireSuperAdmin> },
      { path: 'permissions', element: <RequireSuperAdmin><Permissions /></RequireSuperAdmin> },
      { path: 'audit-logs', element: <AuditLogs /> },
      { path: '2fa', element: <Setup2FA /> },
      { path: 'settings', element: <RequireSuperAdmin><AdminSettings /></RequireSuperAdmin> },
    ],
  },
])

export const AppRouter: React.FC = () => {
  useSessionBootstrap()
  return <RouterProvider router={router} />
}
