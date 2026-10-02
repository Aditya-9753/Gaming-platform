import React, { useState } from 'react'
import { Ban, AlertTriangle } from 'lucide-react'
import { Button } from '../common/Button'
import { ConfirmDialog } from '../common/ConfirmDialog'

export interface SelfExclusionFormProps {
  onExclude?: (days: number, reason: string) => Promise<void> | void
}

export const SelfExclusionForm: React.FC<SelfExclusionFormProps> = ({ onExclude }) => {
  const [days, setDays] = useState('7')
  const [reason, setReason] = useState('Need a break')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const handleConfirm = async () => {
    setIsLoading(true)
    try {
      await onExclude?.(Number(days), reason)
      setConfirmOpen(false)
    } catch {
      return
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      <div className="p-6 rounded-2xl bg-dark-card border border-rose-500/20 shadow-xl space-y-4 text-left">
        <div className="flex items-center gap-2">
          <Ban className="w-5 h-5 text-rose-400" />
          <h4 className="text-base font-bold text-white">Self-Exclusion</h4>
        </div>

        <p className="text-xs text-slate-400">
          Need a temporary or permanent timeout? Self-exclusion immediately blocks wagering for the selected duration and cannot be reversed early.
        </p>

        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-300">Exclusion Duration</label>
          <select
            value={days}
            onChange={(e) => setDays(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-rose-500"
          >
            <option value="7">7 Days (Cool-off)</option>
            <option value="1">24 Hours</option>
            <option value="36500">Permanent</option>
            <option value="30">30 Days</option>
            <option value="90">3 Months</option>
            <option value="180">6 Months</option>
            <option value="365">1 Year</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-300">Reason (Optional)</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-rose-500"
          />
        </div>

        <Button
          type="button"
          variant="danger"
          className="w-full font-bold"
          onClick={() => setConfirmOpen(true)}
          leftIcon={<AlertTriangle className="w-4 h-4" />}
        >
          Request Self-Exclusion
        </Button>
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        title="Confirm Self-Exclusion"
        message={`Are you sure you want to lock your account for ${days} days? This action cannot be revoked before the period ends.`}
        confirmText="Confirm Lockout"
        variant="danger"
        isLoading={isLoading}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  )
}
