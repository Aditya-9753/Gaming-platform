import React, { useEffect } from 'react'
import { HeartHandshake } from 'lucide-react'
import { LimitsForm } from '../../components/responsible-play/LimitsForm'
import { SelfExclusionForm } from '../../components/responsible-play/SelfExclusionForm'
import { SessionReminder } from '../../components/responsible-play/SessionReminder'
import { useUserStore } from '../../store/user.store'
import { responsiblePlayApi } from '../../services/responsible-play.api'
import type { ResponsiblePlayLimits } from '../../types/user.types'
import { showToast } from '../../components/common/Toast'
import { t as tr } from '../../i18n'

export const ResponsiblePlay: React.FC = () => {
  const { limits, setLimits } = useUserStore()

  useEffect(() => {
    responsiblePlayApi.getLimits().then(setLimits).catch(() => {
      showToast({ title: tr('Settings unavailable'), message: tr('Responsible-play preferences could not be loaded.'), type: 'error' })
    })
  }, [setLimits])

  const handleSaveLimits = async (newLimits: Partial<ResponsiblePlayLimits>) => {
    try {
      const updated = await responsiblePlayApi.updateLimits(newLimits)
      setLimits(updated)
    } catch (error) {
      showToast({ title: tr('Could not save settings'), message: tr('Responsible gaming preferences were not saved.'), type: 'error' })
      throw error
    }
  }

  const handleSelfExclude = async (days: number, reason: string) => {
    try {
      await responsiblePlayApi.selfExclude(days, reason)
    } catch (error) {
      showToast({ title: tr('Self-exclusion failed'), message: tr('The server could not activate self-exclusion.'), type: 'error' })
      throw error
    }
  }

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <HeartHandshake className="w-7 h-7" />
        </div>
        <div>
          <h2 className="text-2xl font-black text-white">{tr('Responsible Gaming')}</h2>
          <p className="text-xs text-slate-400">
            {tr('We care about your well-being. Use these tools to stay in control.')}
          </p>
        </div>
      </div>

      {/* Resources Banner */}
      <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-1">
        <strong className="block text-emerald-400">{tr('Need Help?')}</strong>
        <p>
          If gambling is affecting your finances or relationships, please reach out to the{' '}
          <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer" className="underline font-bold">
            {tr('BeGambleAware Helpline')}
          </a>{' '}
          or{' '}
          <a href="https://www.gamblersanonymous.org" target="_blank" rel="noopener noreferrer" className="underline font-bold">
            {tr('Gamblers Anonymous India')}
          </a>
          {tr('. You are not alone.')}
        </p>
      </div>

      <LimitsForm initialLimits={limits || undefined} onSave={handleSaveLimits} />

      <SelfExclusionForm onExclude={handleSelfExclude} />

      {/* Session Reminder (lives hidden unless time triggers) */}
      <SessionReminder sessionLimitMinutes={limits?.sessionTimeLimitMinutes || 60} />
    </div>
  )
}
