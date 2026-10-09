import { useCallback } from 'react'
import { useAuthStore } from '../store/auth.store'
import { authApi } from '../services/auth.api'
import type { LoginCredentials, RegisterCredentials } from '../types/auth.types'
import { showToast } from '../components/common/Toast'
import { t as tr } from '../i18n'

export function useAuth() {
  const { user, isAuthenticated, isLoading, setAuth, logout: storeLogout } = useAuthStore()

  const login = useCallback(async (credentials: LoginCredentials) => {
    const token = await authApi.login(credentials.username, credentials.password, credentials.totpCode)
    const user = await authApi.getCurrentUser()
    setAuth(user, token.access_token)
    showToast({ title: tr('Welcome back!'), message: tr('Logged in as {name}', { name: user.username }), type: 'success' })
    return { user, accessToken: token.access_token }
  }, [setAuth])

  const register = useCallback(async (credentials: RegisterCredentials) => {
    const token = await authApi.register(credentials.username, credentials.password, credentials.ageConfirmed, credentials.email)
    const user = await authApi.getCurrentUser()
    setAuth(user, token.access_token)
    showToast({ title: tr('Account Created!'), message: tr('Welcome, {name}!', { name: user.username }), type: 'success' })
    return { user, accessToken: token.access_token }
  }, [setAuth])

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* ignore */ }
    storeLogout()
  }, [storeLogout])

  return { user, isAuthenticated, isLoading, login, register, logout }
}
