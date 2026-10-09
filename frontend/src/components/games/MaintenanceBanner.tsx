import React from 'react'
import { AlertTriangle } from 'lucide-react'
import { useGameStore } from '../../store/game.store'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'
import { t as tr } from '../../i18n'

/** Shown site-wide while the super admin has maintenance mode on. */
export const MaintenanceBanner: React.FC = () => {
  const { isMaintenance } = useGameStore()
  const { maintenance_mode: on, maintenance_message: message } = usePlatformConfig()

  if (!on && !isMaintenance) return null

  return (
    <div className="bg-amber-500 text-dark-bg px-4 py-2 text-xs font-bold flex items-center justify-center gap-2 text-center" role="status">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>{message || tr('Scheduled system maintenance in progress. Active bets are protected.')}</span>
    </div>
  )
}
