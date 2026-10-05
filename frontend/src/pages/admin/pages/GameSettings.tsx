import React, { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'
import { usePermission } from '../../../hooks/usePermission'
import { getApiErrorMessage } from '../../../utils/apiError'

export const GameSettings: React.FC = () => {
  const [selectedGame, setSelectedGame] = useState('aviator')
  const [houseEdge, setHouseEdge] = useState('3.0')
  const [minBet, setMinBet] = useState('1')
  const [maxBet, setMaxBet] = useState('1000')
  const [countdown, setCountdown] = useState('6')
  const [isActive, setIsActive] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [supportsMargin, setSupportsMargin] = useState(true)
  // House margin and payouts are super-admin only (enforced by the API too)
  const canSetMargin = usePermission().isSuperAdmin() && supportsMargin

  useEffect(() => {
    apiClient.get<{ house_edge_percent: number; min_bet: number; max_bet: number; config: Record<string, unknown>; is_active: boolean; supports_margin?: boolean }>(`/admin/games/${selectedGame}/settings`)
      .then(({ data }) => {
        setHouseEdge((data.house_edge_percent / 100).toString())
        setSupportsMargin(data.supports_margin ?? true)
        setMinBet((data.min_bet / 100).toString())
        setMaxBet((data.max_bet / 100).toString())
        setCountdown(String(data.config.betting_duration_sec ?? 6))
        setIsActive(data.is_active)
      })
      .catch(() => showToast({ title: 'Settings unavailable', message: 'Could not load this game configuration.', type: 'error' }))
  }, [selectedGame])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      await apiClient.patch(`/admin/games/${selectedGame}/settings`, {
        ...(canSetMargin ? { house_edge_percent: Math.round(Number(houseEdge) * 100) } : {}),
        min_bet: Math.round(Number(minBet) * 100),
        max_bet: Math.round(Number(maxBet) * 100),
        ...(selectedGame === 'aviator' ? { config: { betting_duration_sec: Number(countdown) } } : {}),
        is_active: isActive,
      })
      showToast({
        title: 'Settings Saved',
        message: `Updated parameters for ${selectedGame.toUpperCase()}`,
        type: 'success',
      })
    } catch (error) {
      showToast({ title: 'Settings rejected', message: getApiErrorMessage(error, 'Please check limits, timers, and your game-management permission.'), type: 'error' })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Game Parameters & RTP</h1>
        <p className="text-xs text-slate-400">Configure mathematical house edge and stake limits</p>
      </div>

      <form onSubmit={handleSave} className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Select Game</label>
          <select
            value={selectedGame}
            onChange={(e) => setSelectedGame(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-purple-500"
          >
            <option value="aviator">Aviator Crash</option>
            <option value="color">Color Prediction</option>
            <option value="wingo_30s">WinGo 30sec</option>
            <option value="wingo_1m">WinGo 1 Min</option>
            <option value="wingo_3m">WinGo 3 Min</option>
            <option value="wingo_5m">WinGo 5 Min</option>
            <option value="mines">Mines</option>
            <option value="cricket">Cricket Live</option>
          </select>
        </div>

        {supportsMargin ? (
          <Input
            label="House Margin (%)"
            type="number"
            step="0.1"
            value={houseEdge}
            disabled={!canSetMargin}
            onChange={(e) => setHouseEdge(e.target.value)}
            helperText={canSetMargin ? `Applies from the next round. Theoretical RTP: ${(100 - Number(houseEdge)).toFixed(1)}%` : 'Only the super admin can change the house margin'}
          />
        ) : (
          <p className="text-xs text-slate-400">A house margin does not apply to this game.</p>
        )}

        <label className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-elevated p-3 text-sm text-white">
          Game enabled
          <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Min Bet (₹)"
            type="number"
            value={minBet}
            onChange={(e) => setMinBet(e.target.value)}
          />
          <Input
            label="Max Bet (₹)"
            type="number"
            value={maxBet}
            onChange={(e) => setMaxBet(e.target.value)}
          />
        </div>

        {selectedGame === 'aviator' && <Input
          label="Inter-Round Countdown (Seconds)"
          type="number"
          value={countdown}
          onChange={(e) => setCountdown(e.target.value)}
        />}

        <Button
          type="submit"
          variant="primary"
          className="w-full font-bold"
          isLoading={isSaving}
          leftIcon={<Check className="w-4 h-4" />}
        >
          Update Settings
        </Button>
      </form>
    </div>
  )
}
