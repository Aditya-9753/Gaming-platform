import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, Banknote, CheckCircle2, Clock, Copy, History, KeyRound, Plus, QrCode, ShieldCheck, Trash2, XCircle } from 'lucide-react'
import { Button } from '../../components/common/Button'
import { StatusPill } from '../../components/payments/StatusPill'
import { showToast } from '../../components/common/Toast'
import { useIdempotencyKey } from '../../hooks/useIdempotencyKey'
import { paymentsApi, type Beneficiary, type Deposit, type Eligibility, type PaymentConfig, type Withdrawal } from '../../services/payments.api'
import { syncWalletBalance } from '../../services/wallet.api'
import { getApiErrorMessage } from '../../utils/apiError'
import { formatDateTime, formatPaiseToRupee, rupeeToPaise } from '../../utils/formatters'

type Tab = 'deposit' | 'withdraw' | 'history'

const inputCls = 'w-full rounded-xl border border-dark-border bg-dark-elevated px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none'
const QUICK = [200, 500, 1000, 2000, 5000]

const fail = (title: string, error: unknown, fallback = 'Please try again.') =>
  showToast({ title, message: getApiErrorMessage(error, fallback), type: 'error' })

const CopyRow: React.FC<{ label: string; value: string; strong?: boolean }> = ({ label, value, strong }) => (
  <div className="flex items-center justify-between gap-3 rounded-xl bg-dark-elevated px-3 py-2">
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`truncate font-mono ${strong ? 'text-lg font-black text-white' : 'text-sm text-slate-200'}`}>{value}</p>
    </div>
    <button
      type="button"
      aria-label={`Copy ${label}`}
      onClick={() => { void navigator.clipboard?.writeText(value); showToast({ title: `${label} copied`, type: 'success' }) }}
      className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-dark-card hover:text-white"
    >
      <Copy className="h-4 w-4" />
    </button>
  </div>
)

function useCountdown(until?: string) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  if (!until) return null
  const left = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000))
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`
}

// ── Deposit ──────────────────────────────────────────────────────────────────

const ActiveDeposit: React.FC<{ deposit: Deposit; onChange: (d: Deposit | null) => void }> = ({ deposit, onChange }) => {
  const [utr, setUtr] = useState(deposit.utr ?? '')
  const [busy, setBusy] = useState(false)
  const [showStatic, setShowStatic] = useState(false)
  const countdown = useCountdown(deposit.status === 'PENDING' && !deposit.utr ? deposit.expires_at : undefined)

  // Poll while the payment is being verified
  useEffect(() => {
    if (deposit.status !== 'PENDING') return
    const t = window.setInterval(async () => {
      try {
        const fresh = await paymentsApi.deposit(deposit.id)
        if (fresh.status !== deposit.status || fresh.stage !== deposit.stage) {
          onChange(fresh)
          if (fresh.status === 'SUCCESS') {
            showToast({ title: 'Deposit successful', message: `${formatPaiseToRupee(fresh.credited_amount_paise ?? fresh.amount_paise)} added to your wallet`, type: 'success' })
            void syncWalletBalance()
          }
        }
      } catch { /* keep polling */ }
    }, 5000)
    return () => window.clearInterval(t)
  }, [deposit, onChange])

  const submit = async () => {
    setBusy(true)
    try {
      const fresh = await paymentsApi.submitUtr(deposit.id, utr)
      onChange(fresh)
      if (fresh.status === 'SUCCESS') {
        showToast({ title: 'Deposit successful', type: 'success' })
        void syncWalletBalance()
      } else showToast({ title: 'UTR received', message: 'We are verifying your payment with the bank.', type: 'info' })
    } catch (error) { fail('Could not submit UTR', error) } finally { setBusy(false) }
  }

  const cancel = async () => {
    try { onChange(await paymentsApi.cancelDeposit(deposit.id)) } catch (error) { fail('Could not cancel', error) }
  }

  if (deposit.status === 'SUCCESS') {
    return (
      <div className="space-y-3 rounded-2xl border border-emerald-500/40 bg-emerald-950/20 p-6 text-center">
        <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-400" />
        <p className="text-lg font-black text-white">{formatPaiseToRupee(deposit.credited_amount_paise ?? deposit.amount_paise)} added</p>
        <p className="text-xs text-slate-400">Reference {deposit.reference}</p>
        <Button variant="secondary" onClick={() => onChange(null)}>New deposit</Button>
      </div>
    )
  }
  if (deposit.status === 'REJECTED') {
    return (
      <div className="space-y-3 rounded-2xl border border-rose-500/40 bg-rose-950/20 p-6 text-center">
        <XCircle className="mx-auto h-12 w-12 text-rose-400" />
        <p className="text-lg font-black text-white">{deposit.stage}</p>
        {deposit.note && <p className="text-sm text-rose-200">{deposit.note}</p>}
        <p className="text-xs text-slate-400">If money left your account, contact support with reference {deposit.reference}{deposit.utr ? ` and UTR ${deposit.utr}` : ''}.</p>
        <Button variant="secondary" onClick={() => onChange(null)}>New deposit</Button>
      </div>
    )
  }

  const pay = deposit.payment
  return (
    <div className="grid gap-5 rounded-2xl border border-dark-border bg-dark-card p-5 md:grid-cols-[240px_1fr]">
      <div className="space-y-3 text-center">
        {pay && (showStatic && pay.qr_image ? pay.qr_image : pay.qr) ? (
          <img src={(showStatic && pay.qr_image) || pay.qr || ''} alt="Payment QR code" className="mx-auto w-full max-w-[240px] rounded-xl bg-white p-2" />
        ) : (
          <div className="flex aspect-square items-center justify-center rounded-xl bg-dark-elevated text-slate-500"><QrCode className="h-16 w-16" /></div>
        )}
        {pay?.qr_image && (
          <button type="button" onClick={() => setShowStatic((v) => !v)} className="text-[11px] font-bold text-emerald-400 hover:underline">
            {showStatic ? 'Show amount QR' : 'Show merchant QR'}
          </button>
        )}
        {pay && (
          <a href={pay.upi_link} className="block rounded-xl bg-emerald-500 px-3 py-2 text-sm font-black text-dark-bg md:hidden">Open UPI app</a>
        )}
        {countdown && <p className="flex items-center justify-center gap-1 text-xs text-amber-300"><Clock className="h-3.5 w-3.5" /> Pay within {countdown}</p>}
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-black text-white">Step 1 — Pay with any UPI app</h3>
          <StatusPill status={deposit.status} />
        </div>
        <CopyRow label="Pay exactly" value={(deposit.amount_paise / 100).toFixed(2)} strong />
        {deposit.amount_paise % 100 !== 0 && (
          <p className="text-[11px] text-slate-400">The paise in this amount are unique to your request — paying the exact amount lets us credit you automatically.</p>
        )}
        {pay && <CopyRow label={`UPI ID · ${pay.payee_name}`} value={pay.upi_id} />}
        <CopyRow label="Reference (add in UPI note)" value={deposit.reference} />

        <div className="space-y-2 border-t border-dark-border pt-3">
          <h3 className="text-sm font-black text-white">Step 2 — Paid? Enter the UTR</h3>
          <p className="text-[11px] text-slate-400">The 12-digit UPI reference / UTR from your payment app's receipt. It helps us find your payment faster; the money is credited only after the bank confirms it.</p>
          <div className="flex gap-2">
            <input className={inputCls} value={utr} onChange={(e) => setUtr(e.target.value.toUpperCase())} placeholder="e.g. 412345678901" maxLength={40} />
            <Button onClick={submit} isLoading={busy} disabled={utr.replace(/\s/g, '').length < 6 || !deposit.can_submit_utr}>Submit</Button>
          </div>
          <p className="text-xs font-bold text-amber-300">{deposit.stage}{deposit.note ? ` — ${deposit.note}` : ''}</p>
        </div>
        {deposit.can_cancel && (
          <button type="button" onClick={cancel} className="text-xs font-bold text-slate-500 hover:text-rose-300">Cancel this deposit</button>
        )}
      </div>
    </div>
  )
}

const DepositTab: React.FC<{ config: PaymentConfig | null }> = ({ config }) => {
  const [amount, setAmount] = useState('500')
  const [active, setActive] = useState<Deposit | null>(null)
  const [busy, setBusy] = useState(false)
  const [key, rotateKey] = useIdempotencyKey()

  useEffect(() => {
    // Resume the newest unfinished deposit
    paymentsApi.deposits().then(async (page) => {
      const open = page.items.find((d) => d.status === 'PENDING')
      if (open) setActive(await paymentsApi.deposit(open.id))
    }).catch(() => {})
  }, [])

  const create = async () => {
    setBusy(true)
    try {
      setActive(await paymentsApi.createDeposit(rupeeToPaise(amount), key))
      rotateKey()
    } catch (error) { fail('Could not start deposit', error) } finally { setBusy(false) }
  }

  if (active) return <ActiveDeposit deposit={active} onChange={setActive} />
  if (config && !config.enabled) return <p className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-sm text-amber-200">Deposits are paused right now. Please try again later.</p>

  return (
    <div className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
      <label className="block text-xs font-bold uppercase tracking-wider text-slate-400" htmlFor="dep-amount">Amount (₹)</label>
      <input id="dep-amount" className={`${inputCls} text-lg font-black`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
      <div className="flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button key={q} type="button" onClick={() => setAmount(String(q))}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold ${Number(amount) === q ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-dark-border text-slate-300 hover:border-slate-500'}`}>
            ₹{q.toLocaleString('en-IN')}
          </button>
        ))}
      </div>
      {config && <p className="text-[11px] text-slate-500">Min {formatPaiseToRupee(config.deposit_min_paise, false)} · Max {formatPaiseToRupee(config.deposit_max_paise, false)} · QR valid {config.deposit_expiry_minutes} min</p>}
      <Button className="w-full" size="lg" onClick={create} isLoading={busy} leftIcon={<QrCode className="h-5 w-5" />} disabled={!Number(amount)}>Get payment QR</Button>
      <p className="flex items-start gap-2 text-[11px] text-slate-500"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />Your wallet is credited only after the bank confirms the payment. Never share screenshots or OTPs with anyone claiming to be support.</p>
    </div>
  )
}

// ── Withdraw ─────────────────────────────────────────────────────────────────

const PinForm: React.FC<{ hasPin: boolean; onDone: () => void }> = ({ hasPin, onDone }) => {
  const [pin, setPin] = useState('')
  const [confirm, setConfirm] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (pin !== confirm) { showToast({ title: 'PINs do not match', type: 'error' }); return }
    setBusy(true)
    try {
      await paymentsApi.setPin(pin, password)
      showToast({ title: hasPin ? 'PIN changed' : 'PIN set', message: hasPin ? 'Withdrawals unlock again after the security cooling period.' : undefined, type: 'success' })
      setPin(''); setConfirm(''); setPassword('')
      onDone()
    } catch (error) { fail('Could not save PIN', error) } finally { setBusy(false) }
  }
  return (
    <div className="grid gap-2 sm:grid-cols-4">
      <input className={inputCls} type="password" inputMode="numeric" maxLength={6} placeholder="New PIN (4-6 digits)" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
      <input className={inputCls} type="password" inputMode="numeric" maxLength={6} placeholder="Confirm PIN" value={confirm} onChange={(e) => setConfirm(e.target.value.replace(/\D/g, ''))} />
      <input className={inputCls} type="password" placeholder="Account password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
      <Button onClick={save} isLoading={busy} disabled={pin.length < 4 || !password}>{hasPin ? 'Change PIN' : 'Set PIN'}</Button>
    </div>
  )
}

const AddPayoutAccount: React.FC<{ onAdded: () => void }> = ({ onAdded }) => {
  const [method, setMethod] = useState<'BANK' | 'UPI'>('UPI')
  const [form, setForm] = useState({ holder_name: '', account_number: '', ifsc: '', bank_name: '', vpa: '', pin: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const save = async () => {
    setBusy(true)
    try {
      const body: Record<string, string> = { method, holder_name: form.holder_name, pin: form.pin }
      if (method === 'BANK') Object.assign(body, { account_number: form.account_number, ifsc: form.ifsc.toUpperCase(), bank_name: form.bank_name })
      else body.vpa = form.vpa
      await paymentsApi.addBeneficiary(body)
      showToast({ title: 'Payout account added', message: 'It can be used once the security cooling period ends.', type: 'success' })
      setForm({ holder_name: '', account_number: '', ifsc: '', bank_name: '', vpa: '', pin: '' })
      onAdded()
    } catch (error) { fail('Could not add account', error) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-3 rounded-xl border border-dashed border-dark-border p-4">
      <div className="flex gap-2">
        {(['UPI', 'BANK'] as const).map((m) => (
          <button key={m} type="button" onClick={() => setMethod(m)} className={`rounded-lg px-3 py-1.5 text-xs font-bold ${method === m ? 'bg-emerald-500 text-dark-bg' : 'bg-dark-elevated text-slate-300'}`}>
            {m === 'UPI' ? 'UPI ID' : 'Bank account'}
          </button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <input className={inputCls} placeholder="Account holder name (as in bank)" value={form.holder_name} onChange={set('holder_name')} />
        {method === 'UPI' ? (
          <input className={inputCls} placeholder="yourname@okaxis" value={form.vpa} onChange={set('vpa')} />
        ) : (
          <>
            <input className={inputCls} inputMode="numeric" placeholder="Account number" value={form.account_number} onChange={set('account_number')} />
            <input className={inputCls} placeholder="IFSC (e.g. HDFC0001234)" value={form.ifsc} onChange={set('ifsc')} maxLength={11} />
            <input className={inputCls} placeholder="Bank name (optional)" value={form.bank_name} onChange={set('bank_name')} />
          </>
        )}
        <input className={inputCls} type="password" inputMode="numeric" maxLength={6} placeholder="Transaction PIN" value={form.pin} onChange={set('pin')} />
      </div>
      <Button size="sm" onClick={save} isLoading={busy} leftIcon={<Plus className="h-4 w-4" />} disabled={!form.holder_name || form.pin.length < 4}>Save payout account</Button>
      <p className="text-[11px] text-slate-500">Use an account in your own name. For your safety new accounts can receive money only after a cooling period.</p>
    </div>
  )
}

const WithdrawTab: React.FC = () => {
  const [elig, setElig] = useState<Eligibility | null>(null)
  const [accounts, setAccounts] = useState<Beneficiary[]>([])
  const [amount, setAmount] = useState('')
  const [target, setTarget] = useState('')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showPin, setShowPin] = useState(false)
  const [key, rotateKey] = useIdempotencyKey()

  const load = useCallback(async () => {
    try {
      const [e, b] = await Promise.all([paymentsApi.eligibility(), paymentsApi.beneficiaries()])
      setElig(e)
      setAccounts(b)
    } catch (error) { fail('Could not load withdrawal details', error) }
  }, [])
  useEffect(() => { void load() }, [load])

  const usable = useMemo(() => accounts.filter((a) => new Date(a.cooling_until).getTime() <= Date.now()), [accounts])
  useEffect(() => { if (!target && usable[0]) setTarget(usable[0].id) }, [usable, target])

  const submit = async () => {
    setBusy(true)
    try {
      await paymentsApi.requestWithdrawal(rupeeToPaise(amount), target, pin, key)
      rotateKey()
      setAmount(''); setPin('')
      showToast({ title: 'Withdrawal requested', message: 'The amount is on hold until it is paid out.', type: 'success' })
      void syncWalletBalance()
      await load()
    } catch (error) { fail('Withdrawal not accepted', error) } finally { setBusy(false) }
  }

  const remove = async (id: string) => {
    try { await paymentsApi.removeBeneficiary(id); await load() } catch (error) { fail('Could not remove', error) }
  }

  if (!elig) return <p className="text-sm text-slate-400">Loading…</p>
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-dark-border bg-dark-card p-4"><p className="text-[10px] font-bold uppercase text-slate-500">Withdrawable now</p><p className="text-xl font-black text-white">{formatPaiseToRupee(elig.available_paise)}</p></div>
        <div className="rounded-2xl border border-dark-border bg-dark-card p-4"><p className="text-[10px] font-bold uppercase text-slate-500">On hold (pending payouts)</p><p className="text-xl font-black text-amber-300">{formatPaiseToRupee(elig.pending_withdrawal_paise)}</p></div>
        <div className="rounded-2xl border border-dark-border bg-dark-card p-4"><p className="text-[10px] font-bold uppercase text-slate-500">Left today</p><p className="text-xl font-black text-white">{formatPaiseToRupee(elig.daily_amount_left_paise, false)} · {elig.daily_count_left}×</p></div>
      </div>

      {elig.blockers.length > 0 && (
        <ul className="space-y-1 rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-sm text-amber-200">
          {elig.blockers.map((b) => <li key={b}>• {b}</li>)}
        </ul>
      )}

      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-black text-white"><KeyRound className="h-4 w-4 text-emerald-400" />Transaction PIN</h3>
          {elig.pin_set && <button type="button" className="text-xs font-bold text-emerald-400" onClick={() => setShowPin((v) => !v)}>{showPin ? 'Close' : 'Change PIN'}</button>}
        </div>
        {!elig.pin_set ? <PinForm hasPin={false} onDone={load} /> : showPin ? <PinForm hasPin onDone={() => { setShowPin(false); void load() }} /> : <p className="text-xs text-slate-400">PIN is set. It is needed for every withdrawal and payout-account change.</p>}
      </section>

      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-black text-white"><Banknote className="h-4 w-4 text-emerald-400" />Payout accounts</h3>
          {elig.pin_set && accounts.length < 3 && <button type="button" className="text-xs font-bold text-emerald-400" onClick={() => setShowAdd((v) => !v)}>{showAdd ? 'Close' : '+ Add'}</button>}
        </div>
        {accounts.length === 0 && !showAdd && <p className="text-xs text-slate-400">No payout account yet.</p>}
        {accounts.map((a) => {
          const cooling = new Date(a.cooling_until).getTime() > Date.now()
          return (
            <div key={a.id} className="flex items-center justify-between rounded-xl bg-dark-elevated px-3 py-2">
              <div>
                <p className="text-sm font-bold text-white">{a.holder_name} <span className="font-mono text-slate-400">{a.masked}</span></p>
                <p className={`text-[11px] ${cooling ? 'text-amber-300' : 'text-emerald-400'}`}>{cooling ? `Usable from ${formatDateTime(a.cooling_until)}` : 'Ready'}</p>
              </div>
              <button type="button" aria-label="Remove payout account" onClick={() => remove(a.id)} className="rounded-lg p-2 text-slate-500 hover:text-rose-300"><Trash2 className="h-4 w-4" /></button>
            </div>
          )
        })}
        {showAdd && <AddPayoutAccount onAdded={() => { setShowAdd(false); void load() }} />}
      </section>

      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <h3 className="flex items-center gap-2 text-sm font-black text-white"><ArrowUpRight className="h-4 w-4 text-emerald-400" />Withdraw</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          <input className={inputCls} inputMode="decimal" placeholder={`Amount (min ₹${elig.min_paise / 100})`} value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
          <select className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Choose payout account</option>
            {usable.map((a) => <option key={a.id} value={a.id}>{a.holder_name} · {a.masked}</option>)}
          </select>
          <input className={inputCls} type="password" inputMode="numeric" maxLength={6} placeholder="Transaction PIN" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
        </div>
        <Button className="w-full" onClick={submit} isLoading={busy} disabled={!elig.can_withdraw || !Number(amount) || !target || pin.length < 4}>Request withdrawal</Button>
        <p className="text-[11px] text-slate-500">
          The amount is held from your balance immediately and sent to your account after review. If it cannot be paid it is returned to your wallet.
          {elig.turnover_required_paise > 0 && ` Turnover: ${formatPaiseToRupee(elig.wagered_paise, false)} of ${formatPaiseToRupee(elig.turnover_required_paise, false)} played.`}
        </p>
      </section>
    </div>
  )
}

// ── History ──────────────────────────────────────────────────────────────────

const HistoryTab: React.FC = () => {
  const [deposits, setDeposits] = useState<Deposit[]>([])
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([])
  const load = useCallback(async () => {
    try {
      const [d, w] = await Promise.all([paymentsApi.deposits(), paymentsApi.withdrawals()])
      setDeposits(d.items)
      setWithdrawals(w.items)
    } catch (error) { fail('Could not load history', error) }
  }, [])
  useEffect(() => { void load() }, [load])

  const cancel = async (id: string) => {
    try {
      await paymentsApi.cancelWithdrawal(id)
      showToast({ title: 'Withdrawal cancelled', message: 'The amount is back in your wallet.', type: 'success' })
      void syncWalletBalance()
      await load()
    } catch (error) { fail('Could not cancel', error) }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="rounded-2xl border border-dark-border bg-dark-card">
        <h3 className="flex items-center gap-2 border-b border-dark-border p-4 text-sm font-black text-white"><ArrowDownLeft className="h-4 w-4 text-emerald-400" />Deposits</h3>
        {deposits.length === 0 ? <p className="p-4 text-xs text-slate-500">No deposits yet.</p> : deposits.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-3 border-b border-dark-border/60 px-4 py-3 last:border-0">
            <div className="min-w-0">
              <p className="text-sm font-bold text-white">{formatPaiseToRupee(d.credited_amount_paise ?? d.amount_paise)}</p>
              <p className="truncate text-[11px] text-slate-500">{d.reference}{d.utr ? ` · UTR ${d.utr}` : ''} · {formatDateTime(d.created_at)}</p>
              <p className="text-[11px] text-slate-400">{d.stage}{d.note && d.status === 'REJECTED' ? ` — ${d.note}` : ''}</p>
            </div>
            <StatusPill status={d.status} />
          </div>
        ))}
      </section>
      <section className="rounded-2xl border border-dark-border bg-dark-card">
        <h3 className="flex items-center gap-2 border-b border-dark-border p-4 text-sm font-black text-white"><ArrowUpRight className="h-4 w-4 text-rose-400" />Withdrawals</h3>
        {withdrawals.length === 0 ? <p className="p-4 text-xs text-slate-500">No withdrawals yet.</p> : withdrawals.map((w) => (
          <div key={w.id} className="flex items-center justify-between gap-3 border-b border-dark-border/60 px-4 py-3 last:border-0">
            <div className="min-w-0">
              <p className="text-sm font-bold text-white">{formatPaiseToRupee(w.amount_paise)}</p>
              <p className="truncate text-[11px] text-slate-500">{w.payout_to} · {formatDateTime(w.created_at)}</p>
              <p className="text-[11px] text-slate-400">{w.stage}{w.payout_reference ? ` · UTR ${w.payout_reference}` : ''}{w.reject_reason ? ` — ${w.reject_reason}` : ''}</p>
              {w.can_cancel && <button type="button" onClick={() => cancel(w.id)} className="mt-1 text-[11px] font-bold text-rose-300 hover:underline">Cancel request</button>}
            </div>
            <StatusPill status={w.status} />
          </div>
        ))}
      </section>
    </div>
  )
}

export const PaymentsPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(window.location.search).get('tab') as Tab) || 'deposit')
  const [config, setConfig] = useState<PaymentConfig | null>(null)
  useEffect(() => { paymentsApi.config().then(setConfig).catch(() => {}) }, [])

  const tabs: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
    { id: 'deposit', label: 'Deposit', icon: <ArrowDownLeft className="h-4 w-4" /> },
    { id: 'withdraw', label: 'Withdraw', icon: <ArrowUpRight className="h-4 w-4" /> },
    { id: 'history', label: 'History', icon: <History className="h-4 w-4" /> },
  ]
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-white">Deposit & Withdraw</h2>
        <p className="text-xs text-slate-400">Pay by UPI QR; withdraw to your own bank account or UPI ID.</p>
      </div>
      <div className="grid grid-cols-3 gap-2 rounded-xl bg-dark-elevated p-1">
        {tabs.map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={`flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-bold transition-all ${tab === t.id ? 'bg-emerald-500 text-dark-bg shadow' : 'text-slate-400 hover:text-white'}`}>
            {t.icon}<span>{t.label}</span>
          </button>
        ))}
      </div>
      {tab === 'deposit' && <DepositTab config={config} />}
      {tab === 'withdraw' && <WithdrawTab />}
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}
