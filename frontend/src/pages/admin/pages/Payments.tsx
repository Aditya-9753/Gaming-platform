import React, { useCallback, useEffect, useState } from 'react'
import { Banknote, CreditCard, Landmark, QrCode, Search, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { Modal } from '../components/Modal'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { usePermission } from '../../../hooks/usePermission'
import { apiClient } from '../../../services/api'
import { adminPaymentsApi, type AdminDeposit, type AdminWithdrawal, type BankCredit, type PaymentSummary } from '../../../services/payments.api'
import { useAuthStore } from '../../../store/auth.store'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { AccountsPanel } from './payments/AccountsPanel'
import { CreditsPanel } from './payments/CreditsPanel'
import { DepositDetail, DepositsPanel } from './payments/DepositsPanel'
import { actionFailed, ago, inputCls, StatusPill, StepUpDialog } from './payments/shared'
import { WithdrawalDetail, WithdrawalsPanel } from './payments/WithdrawalsPanel'

type Tab = 'deposits' | 'withdrawals' | 'credits' | 'accounts' | 'limits'

// Payment settings editable here (stored in platform settings); *_paise shown in rupees
const LIMITS: Array<[string, string, 'rupees' | 'number' | 'bool']> = [
  ['payments_enabled', 'Accept deposits & withdrawals', 'bool'],
  ['deposit_min_paise', 'Minimum deposit', 'rupees'],
  ['deposit_max_paise', 'Maximum deposit', 'rupees'],
  ['deposit_expiry_minutes', 'QR valid for (minutes)', 'number'],
  ['deposit_unique_paise', 'Unique paise on each deposit (auto-matching)', 'bool'],
  ['manual_deposit_super_threshold_paise', 'Admins may confirm deposits up to', 'rupees'],
  ['withdrawal_min_paise', 'Minimum withdrawal', 'rupees'],
  ['withdrawal_max_paise', 'Maximum withdrawal', 'rupees'],
  ['withdrawal_daily_count', 'Withdrawals per player per day', 'number'],
  ['withdrawal_daily_amount_paise', 'Withdrawal total per player per day', 'rupees'],
  ['withdrawal_high_value_paise', 'Maker-checker from', 'rupees'],
  ['withdrawal_requires_deposit', 'Only depositors can withdraw', 'bool'],
  ['withdrawal_turnover_pct', 'Turnover required (% of deposits)', 'number'],
  ['beneficiary_cooling_hours', 'Cooling period for new payout accounts / PIN change (hours)', 'number'],
]

const LimitsPanel: React.FC = () => {
  const [values, setValues] = useState<Record<string, number | boolean> | null>(null)
  const [draft, setDraft] = useState<Record<string, string | boolean>>({})
  const [saving, setSaving] = useState(false)
  const [integrity, setIntegrity] = useState<{ ok: boolean; problems: Array<Record<string, unknown>>; totals: Record<string, number> } | null>(null)

  const load = useCallback(async () => {
    try {
      const { data } = await apiClient.get<{ values: Record<string, number | boolean> }>('/admin/system-settings')
      setValues(data.values)
      setDraft(Object.fromEntries(LIMITS.map(([k, , kind]) => [k, kind === 'bool' ? Boolean(data.values[k]) : kind === 'rupees' ? String(Number(data.values[k]) / 100) : String(data.values[k])])))
    } catch (error) { actionFailed('Could not load settings', error) }
  }, [])
  useEffect(() => { void load() }, [load])

  const save = async () => {
    setSaving(true)
    try {
      const changes: Record<string, number | boolean> = {}
      LIMITS.forEach(([k, , kind]) => {
        const v = draft[k]
        const value = kind === 'bool' ? Boolean(v) : kind === 'rupees' ? Math.round(Number(v) * 100) : Math.round(Number(v))
        if (values && values[k] !== value) changes[k] = value
      })
      if (Object.keys(changes).length) await apiClient.put('/admin/system-settings', { values: changes })
      showToast({ title: 'Payment limits saved', type: 'success' })
      await load()
    } catch (error) { actionFailed('Could not save', error) } finally { setSaving(false) }
  }

  const check = async () => {
    try { setIntegrity(await adminPaymentsApi.integrity()) } catch (error) { actionFailed('Integrity check failed', error) }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <h3 className="text-sm font-black text-white">Limits & rules</h3>
        {!values ? <p className="text-xs text-slate-400">Loading…</p> : LIMITS.map(([k, label, kind]) => (
          <label key={k} className="flex flex-wrap items-center justify-between gap-2 border-b border-dark-border/50 pb-2 text-xs text-slate-300 sm:flex-nowrap sm:gap-4">
            <span>{label}</span>
            {kind === 'bool' ? (
              <input type="checkbox" checked={Boolean(draft[k])} onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.checked }))} className="h-4 w-4 accent-purple-500" />
            ) : (
              <span className="flex items-center gap-1">{kind === 'rupees' && '₹'}<input className={`${inputCls} w-32 text-right`} inputMode="decimal" value={String(draft[k] ?? '')} onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value.replace(/[^\d.]/g, '') }))} /></span>
            )}
          </label>
        ))}
        <Button variant="accent" size="sm" onClick={save} isLoading={saving}>Save limits</Button>
      </section>
      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <h3 className="flex items-center gap-2 text-sm font-black text-white"><ShieldCheck className="h-4 w-4 text-purple-400" />Ledger integrity</h3>
        <p className="text-[11px] text-slate-400">Checks that every wallet hold equals its open withdrawals, that credited deposits equal DEPOSIT ledger rows, every credited deposit has a bank credit and every completed withdrawal has a payout UTR.</p>
        <Button size="sm" variant="secondary" onClick={check}>Run check</Button>
        {integrity && (
          <div className={`rounded-xl p-3 text-xs ${integrity.ok ? 'bg-emerald-950/30 text-emerald-300' : 'bg-rose-950/30 text-rose-200'}`}>
            {integrity.ok ? 'All checks passed.' : <pre className="whitespace-pre-wrap">{JSON.stringify(integrity.problems, null, 2)}</pre>}
            <p className="mt-2 text-slate-400">Credited all-time {formatPaiseToRupee(integrity.totals.deposits_credited_paise ?? 0)} · held for payouts {formatPaiseToRupee(integrity.totals.withdrawals_held_paise ?? 0)}</p>
          </div>
        )}
      </section>
    </div>
  )
}

const Lookup: React.FC<{ onDeposit: (id: string) => void; onWithdrawal: (id: string) => void }> = ({ onDeposit, onWithdrawal }) => {
  const [q, setQ] = useState('')
  const [result, setResult] = useState<{ deposits: AdminDeposit[]; withdrawals: AdminWithdrawal[]; bank_credits: BankCredit[] } | null>(null)
  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim().length < 3) return
    try { setResult(await adminPaymentsApi.lookup(q.trim())) } catch (error) { actionFailed('Lookup failed', error) }
  }
  const empty = result && !result.deposits.length && !result.withdrawals.length && !result.bank_credits.length
  return (
    <>
      <form onSubmit={run} className="flex w-full gap-2 sm:w-auto">
        <input className={`${inputCls} min-w-0 flex-1 sm:w-72 sm:flex-none`} placeholder="Find by UTR, deposit ref, payment / withdrawal id" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button size="sm" variant="accent" type="submit" leftIcon={<Search className="h-4 w-4" />}>Find</Button>
      </form>
      <Modal open={Boolean(result)} title={`Results for "${q}"`} onClose={() => setResult(null)} wide>
        <div className="space-y-2 text-xs">
          {empty && <p className="text-slate-400">Nothing found (admins only see deposits paid into their own QR accounts).</p>}
          {result?.deposits.map((d) => (
            <button key={d.id} type="button" onClick={() => { setResult(null); onDeposit(d.id) }} className="flex w-full items-center justify-between rounded-xl bg-dark-elevated px-3 py-2 text-left hover:bg-slate-700">
              <span><b className="text-white">Deposit {d.reference}</b> · {d.username} · {formatPaiseToRupee(d.amount_paise)} · UTR {d.utr ?? '-'}</span><StatusPill status={d.status} />
            </button>
          ))}
          {result?.withdrawals.map((w) => (
            <button key={w.id} type="button" onClick={() => { setResult(null); onWithdrawal(w.id) }} className="flex w-full items-center justify-between rounded-xl bg-dark-elevated px-3 py-2 text-left hover:bg-slate-700">
              <span><b className="text-white">Withdrawal</b> · {w.username} · {formatPaiseToRupee(w.amount_paise)} · {w.payout_reference ?? 'no UTR yet'}</span><StatusPill status={w.status} />
            </button>
          ))}
          {result?.bank_credits.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-xl bg-dark-elevated px-3 py-2">
              <span><b className="text-white">Bank credit {c.utr}</b> · {formatPaiseToRupee(c.amount_paise)} · {c.source}{c.remark ? ` · ${c.remark}` : ''}</span><StatusPill status={c.status} />
            </div>
          ))}
        </div>
      </Modal>
    </>
  )
}

const Stat: React.FC<{ label: string; value: string; hint?: string; tone?: string }> = ({ label, value, hint, tone = 'text-white' }) => (
  <div className="rounded-2xl border border-dark-border bg-dark-card p-4">
    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
    <p className={`text-xl font-black ${tone}`}>{value}</p>
    {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
  </div>
)

/** Deposits, withdrawals, bank credits and QR collection accounts for staff. */
export const AdminPayments: React.FC = () => {
  const { hasPermission, isSuperAdmin } = usePermission()
  const myId = useAuthStore((s) => s.user?.id)
  const isSuper = isSuperAdmin()
  const canManage = hasPermission('payment:manage')
  const [tab, setTab] = useState<Tab>('deposits')
  const [summary, setSummary] = useState<PaymentSummary | null>(null)
  const [depositId, setDepositId] = useState<string | null>(null)
  const [withdrawalId, setWithdrawalId] = useState<string | null>(null)

  const loadSummary = useCallback(async () => {
    try { setSummary(await adminPaymentsApi.summary()) } catch { /* cards stay empty */ }
  }, [])
  useEffect(() => {
    void loadSummary()
    const t = window.setInterval(() => { void loadSummary() }, 15000)
    return () => window.clearInterval(t)
  }, [loadSummary])

  const tabs: Array<{ id: Tab; label: string; icon: React.ReactNode; badge?: number; show: boolean }> = [
    { id: 'deposits', label: 'Deposits', icon: <CreditCard className="h-4 w-4" />, badge: summary?.deposits.needs_review, show: true },
    { id: 'withdrawals', label: 'Withdrawals', icon: <Banknote className="h-4 w-4" />, badge: summary?.withdrawals.open_count, show: true },
    { id: 'credits', label: 'Bank credits', icon: <Landmark className="h-4 w-4" />, badge: summary?.deposits.unmatched_bank_credits, show: true },
    { id: 'accounts', label: 'QR accounts', icon: <QrCode className="h-4 w-4" />, badge: summary?.accounts_pending_approval, show: true },
    { id: 'limits', label: 'Limits & integrity', icon: <SlidersHorizontal className="h-4 w-4" />, show: isSuper },
  ]

  return (
    <div className="space-y-6">
      <StepUpDialog />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Payments</h1>
          <p className="text-xs text-slate-400">
            {summary?.scope === 'own_accounts'
              ? 'You see deposits paid into your own QR accounts, and the withdrawal queue.'
              : 'Every deposit, withdrawal, bank credit and QR account.'}{' '}
            Deposits are credited only against a bank credit; withdrawals are completed only by the super admin.
          </p>
        </div>
        <Lookup onDeposit={setDepositId} onWithdrawal={setWithdrawalId} />
      </div>

      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Deposits needing review" value={String(summary.deposits.needs_review)} hint={summary.deposits.oldest_review_at ? `oldest ${ago(summary.deposits.oldest_review_at)}` : 'none waiting'} tone={summary.deposits.needs_review ? 'text-amber-300' : 'text-white'} />
          <Stat label="Credited today" value={formatPaiseToRupee(summary.deposits.credited_today_paise, false)} hint={`${summary.deposits.credited_today_count} deposits · ${summary.deposits.awaiting_payment} awaiting payment`} tone="text-emerald-400" />
          <Stat label="Withdrawals pending" value={`${summary.withdrawals.open_count} · ${formatPaiseToRupee(summary.withdrawals.open_paise, false)}`} hint={summary.withdrawals.oldest_open_at ? `oldest ${ago(summary.withdrawals.oldest_open_at)}` : 'queue empty'} tone={summary.withdrawals.open_count ? 'text-amber-300' : 'text-white'} />
          <Stat label="Paid out today" value={formatPaiseToRupee(summary.withdrawals.paid_today_paise, false)} hint={summary.withdrawals.completed_per_admin_today.map((a) => `${a.admin}: ${a.completed_today}`).join(' · ') || `${summary.withdrawals.paid_today_count} withdrawals`} />
        </div>
      )}

      <div className="-mx-1 flex gap-2 overflow-x-auto rounded-xl bg-dark-elevated p-1 sm:mx-0 sm:flex-wrap">
        {tabs.filter((t) => t.show).map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-4 py-2 text-xs font-bold transition-all ${tab === t.id ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'text-slate-400 hover:text-white'}`}>
            {t.icon}{t.label}
            {Boolean(t.badge) && <span className="rounded-full bg-amber-500 px-1.5 text-[10px] font-black text-dark-bg">{t.badge}</span>}
          </button>
        ))}
      </div>

      {tab === 'deposits' && <DepositsPanel isSuper={isSuper} canManage={canManage} onChanged={loadSummary} />}
      {tab === 'withdrawals' && <WithdrawalsPanel isSuper={isSuper} canManage={canManage} onChanged={loadSummary} />}
      {tab === 'credits' && <CreditsPanel canManage={canManage} myId={myId} isSuper={isSuper} onChanged={loadSummary} />}
      {tab === 'accounts' && <AccountsPanel isSuper={isSuper} canManage={canManage} myId={myId} onChanged={loadSummary} />}
      {tab === 'limits' && isSuper && <LimitsPanel />}

      {depositId && <DepositDetail id={depositId} isSuper={isSuper} canManage={canManage} onClose={() => setDepositId(null)} onChanged={loadSummary} />}
      {withdrawalId && <WithdrawalDetail id={withdrawalId} isSuper={isSuper} canManage={canManage} onClose={() => setWithdrawalId(null)} onChanged={loadSummary} />}
    </div>
  )
}
