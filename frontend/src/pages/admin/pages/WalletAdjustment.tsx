import React, { useState } from 'react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { ConfirmDialog } from '../../../components/common/ConfirmDialog'
import { showToast } from '../../../components/common/Toast'
import { apiClient } from '../../../services/api'
import { rupeeToPaise } from '../../../utils/formatters'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'

export const WalletAdjustment: React.FC = () => {
  const [userId, setUserId] = useState('')
  const [type, setType] = useState<'credit' | 'debit'>('credit')
  const [amountRupees, setAmountRupees] = useState('500')
  const [reason, setReason] = useState('Promotional dispute resolution')
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [key, rotateKey] = useIdempotencyKey()

  const handleConfirm = async () => {
    if (isLoading) return
    setIsLoading(true)
    try {
      const unsignedAmount = rupeeToPaise(Number(amountRupees))
      await apiClient.post(`/admin/users/${encodeURIComponent(userId)}/adjust-balance`, {
        amount: type === 'credit' ? unsignedAmount : -unsignedAmount,
        reason,
      }, { headers: { 'Idempotency-Key': key } })
      rotateKey()
      setIsConfirmOpen(false)
      showToast({
        title: 'Adjustment Executed',
        message: `${type.toUpperCase()} of ₹${amountRupees} was accepted and audited.`,
        type: 'success',
      })
      setUserId('')
    } catch {
      showToast({ title: 'Adjustment failed', message: 'The server did not apply this adjustment. Verify the user ID, amount, and permissions.', type: 'error' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Manual Wallet Adjustment</h1>
        <p className="text-xs text-slate-400">
          Directly credit or debit a player balance with required audit justification
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          setIsConfirmOpen(true)
        }}
        className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4"
      >
        <Input
          label="Target User ID or Phone"
          placeholder="e.g. usr-101 or 9876543210"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          required
        />

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Adjustment Type</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setType('credit')}
              className={`py-2 rounded-xl text-xs font-bold border transition-all ${
                type === 'credit'
                  ? 'bg-emerald-500 text-dark-bg border-emerald-500'
                  : 'bg-dark-elevated text-slate-400 border-dark-border'
              }`}
            >
              Credit (Add Funds)
            </button>
            <button
              type="button"
              onClick={() => setType('debit')}
              className={`py-2 rounded-xl text-xs font-bold border transition-all ${
                type === 'debit'
                  ? 'bg-rose-500 text-white border-rose-500'
                  : 'bg-dark-elevated text-slate-400 border-dark-border'
              }`}
            >
              Debit (Deduct Funds)
            </button>
          </div>
        </div>

        <Input
          label="Amount (₹)"
          type="number"
          min="1"
          value={amountRupees}
          onChange={(e) => setAmountRupees(e.target.value)}
          required
        />

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Mandatory Audit Reason</label>
          <textarea
            rows={3}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl p-3 text-xs text-white focus:outline-none focus:border-purple-500 resize-none"
          />
        </div>

        <Button type="submit" variant="primary" className="w-full font-bold">
          Review & Submit Adjustment
        </Button>
      </form>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Confirm Balance Modification"
        message={`Are you sure you want to ${type.toUpperCase()} ₹${amountRupees} to user ${userId}? This will be permanently recorded in the immutable audit log.`}
        confirmText="Execute Modification"
        variant={type === 'credit' ? 'primary' : 'danger'}
        isLoading={isLoading}
        onConfirm={handleConfirm}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  )
}
