import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '../store/auth.store'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE,
  withCredentials: true, // send httpOnly refresh-token cookie
  timeout: 15000,
})

// ── Request interceptor: attach access token ──────────────────────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: silent token refresh on 401 ─────────────────────────
let isRefreshing = false
let queue: Array<(result: { token?: string; error?: unknown }) => void> = []

apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    if (
      error.response?.status !== 401 ||
      original._retry ||
      original.url?.includes('/auth/login') ||
      original.url?.includes('/auth/register') ||
      original.url?.includes('/auth/refresh')
    ) {
      return Promise.reject(error)
    }
    original._retry = true

    // Read-only partner view opened by support: never fall back to the staff member's own session
    try {
      if (sessionStorage.getItem('aff_impersonation_token')) {
        sessionStorage.removeItem('aff_impersonation_token')
        useAuthStore.getState().logout()
        return Promise.reject(error)
      }
    } catch { /* storage unavailable */ }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        queue.push((result) => {
          if (result.token) resolve(result.token)
          else reject(result.error)
        })
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`
        return apiClient(original)
      })
    }

    isRefreshing = true
    try {
      const { data, status } = await axios.post<{ access_token: string } | undefined>(
        `${API_BASE}/auth/refresh`,
        {},
        { withCredentials: true }
      )
      if (status === 204 || !data?.access_token) {
        throw new Error('Refresh session is missing')
      }
      const accessToken = data.access_token
      useAuthStore.getState().setAccessToken(accessToken)
      queue.forEach((fn) => fn({ token: accessToken }))
      queue = []
      original.headers.Authorization = `Bearer ${accessToken}`
      return apiClient(original)
    } catch {
      queue.forEach((fn) => fn({ error }))
      queue = []
      useAuthStore.getState().logout()
      return Promise.reject(error)
    } finally {
      isRefreshing = false
    }
  }
)
