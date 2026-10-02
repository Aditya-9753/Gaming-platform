import { useCallback } from 'react'
import { useUserStore } from '../store/user.store'
import { userApi } from '../services/user.api'

export function useUser() {
  const { profile, isLoadingProfile, setProfile, setLoadingProfile } = useUserStore()

  const fetchProfile = useCallback(async () => {
    setLoadingProfile(true)
    try {
      const p = await userApi.getProfile()
      setProfile(p)
    } finally {
      setLoadingProfile(false)
    }
  }, [setProfile, setLoadingProfile])

  const updateProfile = useCallback(async (payload: Parameters<typeof userApi.updateProfile>[0]) => {
    const updated = await userApi.updateProfile(payload)
    setProfile(updated)
    return updated
  }, [setProfile])

  return { profile, isLoadingProfile, fetchProfile, updateProfile }
}

