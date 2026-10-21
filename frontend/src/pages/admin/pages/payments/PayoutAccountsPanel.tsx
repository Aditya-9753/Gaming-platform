import React, { useCallback, useEffect, useState } from 'react'
import { Check, Clock } from 'lucide-react'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/toastBus'
import { adminPaymentsApi, type WaitingPayoutAccount } from '../../../../services/payments.api'
import { formatDateTime } from '../../../../utils/formatters'
import { inputCls } from './shared'
import { actionFailed, ago } from './helpers'

/**
 * Players' new payout accounts still in the security wait (24 h by default).
 * The super admin can check an account (e.g. with the player) and make it usable at once.
 */
export const PayoutAccountsPanel: React.FC<{ isSuper: boolean; onChanged: () => void }> = ({ isSuper, onChanged }) => {
  const [items, setItems] = useState<WaitingPayoutAccount[] | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setItems(await adminPaymentsApi.payoutAccounts()) } catch (error) { actionFailed('Could not load payout accounts', error) }
  }, [])
  // oxlint-disable-next-line react/set-state-in-effect -- loads data from the server
  useEffect(() => { void load() }, [load])

  const approve = async (account: WaitingPayoutAccount) => {
    setBusy(account.id)
    try {
      const note = notes[account.id]?.trim() || ''
      await adminPaymentsApi.approvePayoutAccount(account.id, note.length >= 3 ? note : undefined)
      showToast({ title: 'Payout account approved', message: `${account.username} can withdraw to ${account.masked} now.`, type: 'success' })
      await load()
      onChanged()
    } catch (error) { actionFailed('Not approved', error) } finally { setBusy(null) }
  }

  return (
    <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
      <div>
        <h2 className="text-sm font-black text-white">New payout accounts waiting</h2>
        <p className="text-xs text-slate-400">
          A new bank account or UPI id can receive withdrawals only after the security wait. Before approving early, make sure the
          account really belongs to the player (for example by calling them).{!isSuper && ' Only the super admin can approve.'}
        </p>
      </div>
      {items === null ? <p className="text-sm text-slate-400">Loading…</p> : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-dark-border px-4 py-6 text-center text-sm text-slate-500">No payout account is waiting.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-dark-elevated px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-white">{a.holder_name} <span className="font-mono text-slate-400">{a.masked}</span>{a.bank_name ? <span className="text-slate-500"> · {a.bank_name}</span> : null}</p>
                <p className="text-[11px] text-slate-400">Player <b className="text-slate-200">{a.username}</b> · added {ago(a.created_at)}</p>
                <p className="flex items-center gap-1 text-[11px] text-amber-300"><Clock className="h-3 w-3" />Usable automatically from {a.usable_from ? formatDateTime(a.usable_from) : '—'}</p>
              </div>
              {isSuper && (
                <div className="flex w-full gap-2 sm:w-auto">
                  <input className={`${inputCls} sm:w-56`} placeholder="Note (optional), e.g. checked by call" value={notes[a.id] || ''}
                    onChange={(e) => setNotes((n) => ({ ...n, [a.id]: e.target.value }))} maxLength={200} />
                  <Button size="sm" onClick={() => approve(a)} isLoading={busy === a.id} leftIcon={<Check className="h-4 w-4" />}>Approve now</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
