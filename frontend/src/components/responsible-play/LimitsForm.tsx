import React, { useEffect, useState } from 'react'
import { ShieldAlert, Check } from 'lucide-react'
import { Button } from '../common/Button'
import { Input } from '../common/Input'
import { showToast } from '../common/Toast'
import type { ResponsiblePlayLimits } from '../../types/user.types'
import { formatPaiseToRupee, rupeeToPaise } from '../../utils/formatters'

export interface LimitsFormProps {
  initialLimits?: ResponsiblePlayLimits
  onSave?: (limits: Partial<ResponsiblePlayLimits>) => void
}

export const LimitsForm: React.FC<LimitsFormProps> = ({ initialLimits, onSave }) => {
  const [dailyBet, setDailyBet] = useState(
    initialLimits?.dailyBetLimitPaise ? (initialLimits.dailyBetLimitPaise / 100).toString() : ''
  )
  const [dailyLoss, setDailyLoss] = useState(
    initialLimits?.dailyLossLimitPaise ? (initialLimits.dailyLossLimitPaise / 100).toString() : ''
  )
  const [sessionLimit, setSessionLimit] = useState(initialLimits?.sessionTimeLimitMinutes?.toString() || '60')
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (!initialLimits) return
    setDailyBet(initialLimits.dailyBetLimitPaise ? (initialLimits.dailyBetLimitPaise / 100).toString() : '')
    setDailyLoss(initialLimits.dailyLossLimitPaise ? (initialLimits.dailyLossLimitPaise / 100).toString() : '')
    setSessionLimit(initialLimits.sessionTimeLimitMinutes?.toString() || '60')
  }, [initialLimits])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      const payload: Partial<ResponsiblePlayLimits> = {
        dailyBetLimitPaise: dailyBet ? rupeeToPaise(Number(dailyBet)) : undefined,
        dailyLossLimitPaise: dailyLoss ? rupeeToPaise(Number(dailyLoss)) : undefined,
        sessionTimeLimitMinutes: Number(sessionLimit),
      }
      await onSave?.(payload)
      showToast({
        title: 'Limits Saved',
        message: 'Your server-backed daily wagering and loss limits are active.',
        type: 'success',
      })
    } catch {
      showToast({ title: 'Could not save limits', message: 'Please check your values and try again.', type: 'error' })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4 text-left"
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="w-5 h-5 text-emerald-400" />
        <h4 className="text-base font-bold text-white">Daily & Session Limits</h4>
      </div>

      <p className="text-xs text-slate-400">
        Set daily wagering and loss boundaries to support safer play.
      </p>

      <Input
        label="Daily Bet Limit (₹)"
        type="number"
        value={dailyBet}
        onChange={(e) => setDailyBet(e.target.value)}
        helperText={dailyBet ? `Current limit: ${formatPaiseToRupee(rupeeToPaise(Number(dailyBet) || 0))}` : 'Leave blank for no daily bet limit'}
      />

      <Input
        label="Daily Loss Limit (₹)"
        type="number"
        value={dailyLoss}
        onChange={(e) => setDailyLoss(e.target.value)}
        helperText={dailyLoss ? `Current limit: ${formatPaiseToRupee(rupeeToPaise(Number(dailyLoss) || 0))}` : 'Leave blank for no daily loss limit'}
      />

      <Input
        label="Session Reminder Interval (Minutes)"
        type="number"
        value={sessionLimit}
        onChange={(e) => setSessionLimit(e.target.value)}
        helperText="A reminder pop-up will notify you when you exceed this continuous play time."
      />

      <Button
        type="submit"
        variant="primary"
        className="w-full font-bold"
        isLoading={isSaving}
        leftIcon={<Check className="w-4 h-4" />}
      >
        Save Limits
      </Button>
    </form>
  )
}
