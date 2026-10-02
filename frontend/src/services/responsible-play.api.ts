import { apiClient } from './api'
import type { ResponsiblePlayLimits } from '../types/user.types'

export const responsiblePlayApi = {
  getLimits: async (): Promise<ResponsiblePlayLimits> => {
    const { data } = await apiClient.get<{ limits: Record<string, number | null>; session_reminders: { interval_minutes: number; enabled: boolean }; self_exclusion?: { ends_at?: string | null } }>('/responsible-play')
    return {
      dailyBetLimitPaise: data.limits.daily_bet_limit_paise ?? undefined,
      dailyLossLimitPaise: data.limits.daily_loss_limit_paise ?? undefined,
      sessionTimeLimitMinutes: data.session_reminders.enabled ? data.session_reminders.interval_minutes : undefined,
      selfExcludedUntil: data.self_exclusion?.ends_at ?? null,
    }
  },

  updateLimits: async (payload: Partial<ResponsiblePlayLimits>): Promise<ResponsiblePlayLimits> => {
    const limits: Record<string, number | null> = {}
    if (payload.dailyBetLimitPaise !== undefined) limits.daily_bet_limit_paise = payload.dailyBetLimitPaise ?? null
    if (payload.dailyLossLimitPaise !== undefined) limits.daily_loss_limit_paise = payload.dailyLossLimitPaise ?? null
    const { data } = await apiClient.post<{ limits: Record<string, number | null> }>('/responsible-play/limits', limits)
    if (payload.sessionTimeLimitMinutes !== undefined) {
      await apiClient.post('/responsible-play/session-reminders', {
        interval_minutes: payload.sessionTimeLimitMinutes,
        enabled: true,
      })
    }
    return {
      dailyBetLimitPaise: data.limits.daily_bet_limit_paise ?? undefined,
      dailyLossLimitPaise: data.limits.daily_loss_limit_paise ?? undefined,
      sessionTimeLimitMinutes: payload.sessionTimeLimitMinutes,
    }
  },

  selfExclude: async (days: number, reason: string): Promise<void> => {
    await apiClient.post('/responsible-play/self-exclusion', {
      period: days === 1 ? '24h' : days === 7 ? '7d' : days >= 36500 ? 'permanent' : undefined,
      duration_days: days === 1 || days === 7 || days >= 36500 ? undefined : days,
      reason,
    })
  },
}
