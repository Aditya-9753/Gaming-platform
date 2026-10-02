import { apiClient } from './api'
import type { FairnessVerificationInput, FairnessVerificationResult } from '../types/fairness.types'

export const fairnessApi = {
  verifyRound: async (payload: FairnessVerificationInput): Promise<FairnessVerificationResult> => {
    const { data } = await apiClient.post<FairnessVerificationResult>('/fairness/verify', payload)
    return data
  },

  getRoundFairnessData: async (gameId: string, roundId: string): Promise<FairnessVerificationInput> => {
    const { data } = await apiClient.get<FairnessVerificationInput>(`/fairness/${gameId}/${roundId}`)
    return data
  },

  rotateClientSeed: async (newSeed: string): Promise<{ clientSeed: string }> => {
    const { data } = await apiClient.post<{ clientSeed: string }>('/fairness/seed/rotate', { newSeed })
    return data
  },
}

