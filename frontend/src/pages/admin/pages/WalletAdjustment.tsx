import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, UserRound } from 'lucide-react'
import { Input } from '../../../components/common/Input'
import { Button } from '../../../components/common/Button'
import { ConfirmDialog } from '../../../components/common/ConfirmDialog'
import { showToast } from '../../../components/common/toastBus'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'

interface Target {
  id: string
  player_id: string
  username: string
  email: string | null
  phone?: string | null
  role: string | null
  is_active: boolean
  balance_paise: number | null
  has_wallet: boolean
}

export const WalletAdjustment: React.FC = () => {
  // Opened from a player's page: /admin/wallet-adjustment?user=<number or username>
  const [params] = useSearchParams()
  const [query, setQuery] = useState(() => params.get('user') || '')
  const [target, setTarget] = useState<Target | null>(null)
  const [finding, setFinding] = useState(false)
  const [findError, setFindError] = useState<string | null>(null)
  const [type, setType] = useState<'credit' | 'debit'>('credit')
  const [amountRupees, setAmountRupees] = useState('500')
  const [reason, setReason] = useState('Promotional dispute resolution')
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [key, rotateKey] = useIdempotencyKey()

  // Resolve what the admin typed (username, email, player ID shown in the app, or full id) to one player
  const find = async (): Promise<Target | null> => {
    const q = query.trim()
    if (!q) return null
    setFinding(true)
    setFindError(null)
    try {
      const { data } = await apiClient.get<Target>('/admin/users/lookup', { params: { q } })
      setTarget(data)
      return data
    } catch (error) {
      setTarget(null)
      setFindError(getApiErrorMessage(error, 'Player not found'))
      return null
    } finally {
      setFinding(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (query.trim()) void find() }, [])

  const amountPaise = Number(amountRupees) > 0 ? rupeeToPaise(Number(amountRupees)) : 0
  const problemFor = (t: Target | null) => !t ? null
    : !t.has_wallet ? 'This account has no wallet (staff accounts cannot be adjusted).'
      : !amountPaise ? 'Enter an amount above ₹0.'
        : type === 'debit' && t.balance_paise !== null && amountPaise > t.balance_paise
          ? `The player has only ${formatPaiseToRupee(t.balance_paise, false)}; a debit cannot go below zero.`
          : reason.trim().length < 5 ? 'Write a reason of at least 5 characters.' : null
  const problem = problemFor(target)

  const handleConfirm = async () => {
    if (isLoading || !target) return
    setIsLoading(true)
    try {
      const { data } = await apiClient.post<{ transaction_id: string; new_balance: number }>(
        `/admin/users/${encodeURIComponent(target.id)}/adjust-balance`,
        { amount: type === 'credit' ? amountPaise : -amountPaise, reason: reason.trim() },
        { headers: { 'Idempotency-Key': key } },
      )
      rotateKey()
      setIsConfirmOpen(false)
      showToast({
        title: 'Adjustment Executed',
        message: `${type.toUpperCase()} of ₹${amountRupees} for ${target.username}. New balance ${formatPaiseToRupee(data.new_balance, false)}.`,
        type: 'success',
      })
      setTarget({ ...target, balance_paise: data.new_balance })
    } catch (error) {
      setIsConfirmOpen(false)
      showToast({ title: 'Adjustment failed', message: getApiErrorMessage(error, 'The server did not apply this adjustment.'), type: 'error', duration: 8000 })
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
        onSubmit={async (e) => {
          e.preventDefault()
          const found = target && target.username.toLowerCase() === query.trim().toLowerCase() ? target : await find()
          if (found && !problemFor(found)) setIsConfirmOpen(true)
        }}
        className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4"
      >
        <div className="space-y-1.5">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label="Player (mobile number, username, email or player ID)"
                placeholder="e.g. 9876543210 or Devendra26"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setTarget(null); setFindError(null) }}
                onBlur={() => { if (query.trim() && !target) void find() }}
                required
              />
            </div>
            <Button type="button" variant="secondary" onClick={() => void find()} isLoading={finding} leftIcon={<Search className="h-4 w-4" />}>Find</Button>
          </div>
          <p className="text-[11px] text-slate-500">The player ID is the 8-character ID shown under the player's name in their app.</p>
          {findError && <p className="rounded-xl bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{findError}</p>}
          {target && (
            <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
              <UserRound className="h-8 w-8 shrink-0 rounded-full bg-dark-elevated p-1.5 text-emerald-300" />
              <div className="min-w-0 flex-1 text-xs">
                <p className="font-bold text-white">{target.username} <span className="font-mono text-slate-400">ID {target.player_id}</span>
                  {!target.is_active && <span className="ml-2 rounded bg-rose-500/20 px-1.5 text-rose-300">suspended</span>}</p>
                <p className="truncate text-slate-400">{target.phone ? `+91 ${target.phone.slice(3)} · ` : ''}{target.email || '—'} · {target.role || 'USER'}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase text-slate-500">Balance</p>
                <p className="font-black text-white">{target.balance_paise === null ? '—' : formatPaiseToRupee(target.balance_paise, false)}</p>
              </div>
            </div>
          )}
        </div>

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
          max="50000"
          value={amountRupees}
          onChange={(e) => setAmountRupees(e.target.value)}
          required
        />

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300">Mandatory Audit Reason</label>
          <textarea
            rows={3}
            required
            minLength={5}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl p-3 text-xs text-white focus:outline-none focus:border-purple-500 resize-none"
          />
        </div>

        {problem && <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-200">{problem}</p>}
        <Button type="submit" variant="primary" className="w-full font-bold" isLoading={finding} disabled={Boolean(problem)}>
          Review & Submit Adjustment
        </Button>
      </form>

      <ConfirmDialog
        isOpen={isConfirmOpen && target !== null}
        title="Confirm Balance Modification"
        message={target ? `Are you sure you want to ${type.toUpperCase()} ₹${amountRupees} ${type === 'credit' ? 'to' : 'from'} ${target.username} (ID ${target.player_id})? Balance now ${target.balance_paise === null ? '—' : formatPaiseToRupee(target.balance_paise, false)}. This will be permanently recorded in the immutable audit log.` : ''}
        confirmText="Execute Modification"
        variant={type === 'credit' ? 'primary' : 'danger'}
        isLoading={isLoading}
        onConfirm={handleConfirm}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  )
}
