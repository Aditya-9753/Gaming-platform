import React, { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { Badge, Btn, Card, ConfirmPrompt, Empty, ErrorBox, Field, Modal, Money, Spinner, StatusDot, Table, Tabs, Td, inputCls } from '../../components/affiliate/ui'
import { DisplayCurrencyContext, formatMoney, cx, dateOnly, dateTime, toastError, useAsync } from '../../components/affiliate/helpers'
import { showToast } from '../../components/common/toastBus'
import { partnerApi } from '../../services/affiliate.api'
import type { LedgerEntry, Withdrawal } from '../../types/affiliate.types'
import { useT } from './i18n'
import { usePartnerStore } from './partner.store'
import { useNow } from '../../hooks/useNow'

const METHOD_LABEL: Record<string, string> = {
  EWALLET_EMAIL: 'E-wallet (email)', USDT_TRC20: 'USDT (TRC20)', BANK: 'Bank transfer', UPI: 'UPI', OTHER: 'Other',
}
const IDENTIFIER_HINT: Record<string, string> = {
  EWALLET_EMAIL: 'name@example.com', USDT_TRC20: 'T… (34 characters)', BANK: 'Account number / IBAN', UPI: 'name@bank', OTHER: 'Payout details',
}

export const PartnerWithdrawal: React.FC = () => {
  const t = useT()
  const reloadMe = usePartnerStore((s) => s.load)
  const wallet = useAsync(() => partnerApi.wallet(), [])
  const methods = useAsync(() => partnerApi.methods(), [])
  const auto = useAsync(() => partnerApi.autoWithdrawal(), [])
  const history = useAsync(() => partnerApi.withdrawals(), [])
  const [tab, setTab] = useState('withdraw')
  const [amount, setAmount] = useState('')
  const [methodId, setMethodId] = useState<number | null>(null)
  const [prompt, setPrompt] = useState<null | { title: string; message?: string; run: () => Promise<void> }>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [idemKey, setIdemKey] = useState(() => crypto.randomUUID())
  const now = useNow()

  const currency = React.useContext(DisplayCurrencyContext)
  // "20.00 $ (≈ ₹1,700.00)" while the portal shows rupees; just "20.00 $" otherwise
  const usdAnd = (value: string | number) => `${Number(value).toFixed(2)} $${currency.code === 'INR' ? ` (≈ ${formatMoney(value, currency)})` : ''}`
  const activeMethods = methods.data?.items || []
  const method = activeMethods.find((m) => m.id === methodId) || activeMethods.find((m) => m.is_default) || activeMethods[0]
  const refresh = () => { void wallet.reload(); void history.reload(); void auto.reload(); void reloadMe() }

  if (wallet.loading && !wallet.data) return <Spinner />
  if (wallet.error) return <ErrorBox message={wallet.error} onRetry={wallet.reload} />
  const w = wallet.data!
  const coolingDown = method && new Date(method.usable_after).getTime() > now

  const withdraw = () => setPrompt({
    title: t('Withdraw {amount}', { amount: usdAnd(amount) }),
    message: method ? t('To {destination}', { destination: method.destination }) : undefined,
    run: async () => {
      try {
        await partnerApi.requestWithdrawal({ amount, method_id: method?.id }, idemKey)
        showToast({ title: t('Withdrawal requested'), message: t('Finance will review it shortly.'), type: 'success' })
        setAmount('')
        setIdemKey(crypto.randomUUID())
        setPrompt(null)
        refresh()
      } catch (e) { toastError(e, t('Withdrawal not created')) }
    },
  })

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('withdrawal')}</h1>
      <div className="grid grid-cols-3 gap-2">
        {([['available', w.available], ['pending', w.pending], ['reserved', w.reserved]] as const).map(([key, value]) => (
          <div key={key} className={cx('rounded-2xl border p-3', key === 'available' ? 'border-brand-blue/40 bg-brand-blue/10' : 'border-dark-border bg-dark-card')}>
            <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{t(key)}</div>
            <Money value={value} className="text-base font-black sm:text-xl" />
          </div>
        ))}
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'withdraw', label: t('withdraw') }, { id: 'methods', label: t('Payout methods') },
        { id: 'ledger', label: t('Transactions') }, { id: 'statements', label: t('Statements') }]} />

      {tab === 'withdraw' && (
        <>
          <Card>
            {method ? (
              <button type="button" onClick={() => setTab('methods')} className="mb-3 w-full rounded-xl border border-dark-border bg-dark-bg p-3 text-left">
                <div className="text-[11px] text-slate-400">{t(METHOD_LABEL[method.type] || method.type)} · {method.label}</div>
                <div className="font-bold">{method.destination}</div>
                {coolingDown && <div className="mt-1 text-[11px] text-amber-300">{t('Usable from {time} (security cool-down)', { time: dateTime(method.usable_after) })}</div>}
              </button>
            ) : (
              <Btn tone="ghost" className="mb-3 w-full" onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" />{t('Add a payout method')}</Btn>
            )}
            {activeMethods.length > 1 && (
              <select value={method?.id} onChange={(e) => setMethodId(Number(e.target.value))} className={cx(inputCls, 'mb-3')} aria-label="Payout method">
                {activeMethods.map((m) => <option key={m.id} value={m.id}>{m.label} · {m.destination}</option>)}
              </select>
            )}
            <Field label={`${t('amount')} (USD)`} hint={w.withdraw_blocked_reason ? undefined : t('Minimum {amount}', { amount: usdAnd(w.min_payout) })}>
              <div className="flex gap-2">
                <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} className={inputCls} placeholder="0.00" />
                <Btn tone="ghost" onClick={() => setAmount(Math.max(0, Math.floor(Number(w.available) * 100) / 100).toFixed(2))}>{t('Max')}</Btn>
              </div>
            </Field>
            {w.withdraw_blocked_reason && (
              <p className="mt-2 text-xs text-amber-300">
                {w.withdraw_blocked_reason.startsWith('Minimum payout') ? t('Minimum payout is {amount}', { amount: usdAnd(w.min_payout) }) : t(w.withdraw_blocked_reason)}
              </p>
            )}
            <Btn className="mt-3 w-full" disabled={!w.can_withdraw || !method || !Number(amount) || Boolean(coolingDown)} onClick={withdraw}>{t('withdraw')}</Btn>
            <AutoToggle state={auto} methods={activeMethods} onPrompt={setPrompt} minPayout={w.min_payout} />
          </Card>
          <Card title={t('history')}>
            <HistoryList items={history.data?.items || []} loading={history.loading && !history.data} onCancel={async (id) => {
              try { await partnerApi.cancelWithdrawal(id); refresh() } catch (e) { toastError(e) }
            }} />
          </Card>
        </>
      )}

      {tab === 'methods' && (
        <Card title={t('Payout methods')} actions={<Btn small onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" />{t('Add')}</Btn>}>
          <p className="mb-3 text-xs text-slate-400">{t('Details are stored encrypted and shown masked. A new or changed method can be used after a 24-hour cool-down.')}</p>
          <div className="space-y-2">
            {activeMethods.map((m) => (
              <div key={m.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-dark-border p-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-slate-400">{t(METHOD_LABEL[m.type] || m.type)} · {m.label}</div>
                  <div className="font-bold">{m.destination}</div>
                  {new Date(m.usable_after).getTime() > now && <div className="text-[11px] text-amber-300">{t('Usable from {time}', { time: dateTime(m.usable_after) })}</div>}
                </div>
                {m.is_default ? <Badge tone="blue">{t('Default')}</Badge> : (
                  <Btn tone="ghost" small onClick={async () => { try { await partnerApi.updateMethod(m.id, { is_default: true }); void methods.reload() } catch (e) { toastError(e) } }}>{t('Make default')}</Btn>
                )}
                <Btn tone="ghost" small onClick={() => setPrompt({ title: t('Remove payout method'), message: m.destination, run: async () => {
                  try { await partnerApi.updateMethod(m.id, { status: 'ARCHIVED' }); setPrompt(null); void methods.reload() } catch (e) { toastError(e) }
                } })}>{t('Remove')}</Btn>
              </div>
            ))}
            {!activeMethods.length && <Empty>{t('No payout methods yet.')}</Empty>}
          </div>
        </Card>
      )}

      {tab === 'ledger' && <LedgerList />}
      {tab === 'statements' && <Statements />}

      <AddMethodModal open={addOpen} onClose={() => setAddOpen(false)}
        onSaved={() => { setAddOpen(false); void methods.reload() }} />
      <ConfirmPrompt open={prompt !== null} title={prompt?.title} message={prompt?.message} onClose={() => setPrompt(null)} onConfirm={() => prompt!.run()} />
    </div>
  )
}

const AutoToggle: React.FC<{
  state: { data: { enabled: boolean; method_id: number | null; min_amount: string } | null; reload: () => Promise<void> }
  methods: Array<{ id: number; label: string; destination: string }>
  minPayout: string
  onPrompt: (p: { title: string; message?: string; run: () => Promise<void> } | null) => void
}> = ({ state, methods, minPayout, onPrompt }) => {
  const t = useT()
  const enabled = Boolean(state.data?.enabled)
  const [min, setMin] = useState<string>('')
  const toggle = () => onPrompt({
    title: enabled ? t('Turn off auto-withdrawal') : t('Turn on auto-withdrawal'),
    run: async () => {
      try {
        await partnerApi.setAutoWithdrawal({ enabled: !enabled, method_id: state.data?.method_id || methods[0]?.id, min_amount: min || state.data?.min_amount || minPayout })
        onPrompt(null)
        await state.reload()
      } catch (e) { toastError(e) }
    },
  })
  return (
    <div className="mt-4 space-y-2 rounded-xl border border-dark-border p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-bold">{t('autoWithdrawal')}</div>
          <div className="text-[11px] text-slate-400">{t('After each settlement, the full available balance is paid out when it is at least {amount}.', { amount: `${state.data?.min_amount || minPayout} $` })}</div>
        </div>
        <button type="button" role="switch" aria-checked={enabled} onClick={toggle} disabled={!methods.length}
          className={cx('relative h-7 w-12 shrink-0 rounded-full transition disabled:opacity-40', enabled ? 'bg-emerald-500' : 'bg-slate-600')}>
          <span className={cx('absolute top-0.5 h-6 w-6 rounded-full bg-white transition', enabled ? 'left-[22px]' : 'left-0.5')} />
        </button>
      </div>
      {!enabled && methods.length > 0 && (
        <input inputMode="decimal" value={min} onChange={(e) => setMin(e.target.value.replace(/[^0-9.]/g, ''))} placeholder={t('Minimum amount (≥ {amount})', { amount: minPayout })} className={inputCls} />
      )}
    </div>
  )
}

const HistoryList: React.FC<{ items: Withdrawal[]; loading: boolean; onCancel: (id: number) => void }> = ({ items, loading, onCancel }) => {
  const t = useT()
  if (loading) return <Spinner />
  if (!items.length) return <Empty>{t('No withdrawals yet')}</Empty>
  return (
    <ul className="divide-y divide-dark-border">
      {items.map((wd) => (
        <li key={wd.id} className="flex items-center gap-3 py-3">
          <StatusDot status={wd.status} />
          <div className="min-w-0 flex-1 text-[11px] text-slate-400">
            <div>{t('requested')}: {dateTime(wd.requested_at)}</div>
            <div>{t('processed')}: {dateTime(wd.processed_at)}</div>
            <div className="truncate">{wd.destination}{wd.source === 'AUTO' ? ` · ${t('auto')}` : ''}</div>
            {wd.rejection_reason && <div className="text-rose-300">{wd.rejection_reason}</div>}
          </div>
          <div className="text-right">
            <Money value={wd.amount} className="block text-sm font-black" />
            <span className="text-[10px] uppercase text-slate-500">{wd.status.replace('_', ' ')}</span>
            {wd.status === 'PENDING' && <button type="button" onClick={() => onCancel(wd.id)} className="block text-[11px] font-bold text-rose-300 underline">{t('Cancel')}</button>}
          </div>
        </li>
      ))}
    </ul>
  )
}

const AddMethodModal: React.FC<{ open: boolean; onClose: () => void; onSaved: () => void }> = ({ open, onClose, onSaved }) => {
  const t = useT()
  const [form, setForm] = useState({ type: 'EWALLET_EMAIL', label: '', account_name: '', account_identifier: '' })
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} title={t('Add payout method')} onClose={onClose}>
      <div className="space-y-3">
        <Field label={t('Type')}>
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className={inputCls}>
            {Object.entries(METHOD_LABEL).map(([id, label]) => <option key={id} value={id}>{t(label)}</option>)}
          </select>
        </Field>
        <Field label={t('Details')}><input value={form.account_identifier} onChange={(e) => setForm({ ...form, account_identifier: e.target.value })} className={inputCls} placeholder={t(IDENTIFIER_HINT[form.type])} /></Field>
        <Field label={t('Account holder name')}><input value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })} className={inputCls} /></Field>
        <Field label={t('Label (optional)')}><input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} className={inputCls} /></Field>
        <Btn className="w-full" busy={busy} disabled={!form.account_identifier} onClick={async () => {
          setBusy(true)
          try {
            await partnerApi.addMethod({ ...form, label: form.label || undefined, account_name: form.account_name || undefined })
            setForm({ type: 'EWALLET_EMAIL', label: '', account_name: '', account_identifier: '' })
            onSaved()
          } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>{t('Save')}</Btn>
      </div>
    </Modal>
  )
}

const TYPE_LABEL: Record<string, string> = {
  COMMISSION_CPA: 'CPA', COMMISSION_REVSHARE: 'Revshare', SUBPARTNER_COMMISSION: 'Subpartner commission', COMMISSION_ADJUSTMENT: 'Commission change',
  PERIOD_SETTLE: 'Period settled', CARRYOVER_WRITEOFF: 'Negative balance written off', WITHDRAWAL_RESERVE: 'Withdrawal reserved',
  WITHDRAWAL_RELEASE: 'Withdrawal returned', WITHDRAWAL_PAID: 'Withdrawal paid', MANUAL_ADJUSTMENT: 'Adjustment',
}

const LedgerList: React.FC = () => {
  const t = useT()
  const [items, setItems] = useState<LedgerEntry[]>([])
  const [cursor, setCursor] = useState<number | null | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const load = async (next?: number) => {
    setBusy(true)
    try {
      const page = await partnerApi.transactions(next)
      setItems((prev) => (next ? [...prev, ...page.items] : page.items))
      setCursor(page.next_cursor)
    } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [])
  return (
    <Card title={t('Transactions')}>
      <Table head={[t('Date'), t('Type'), t('Balance'), t('Amount'), t('After')]} empty={!items.length && !busy}>
        {items.map((e) => (
          <tr key={e.id}>
            <Td>{dateTime(e.created_at)}</Td>
            <Td><div className="font-bold">{t(TYPE_LABEL[e.type] || e.type)}</div><div className="max-w-[220px] truncate text-[10px] text-slate-500">{e.description}</div></Td>
            <Td><Badge tone={e.bucket === 'AVAILABLE' ? 'green' : e.bucket === 'PENDING' ? 'amber' : 'blue'}>{e.bucket}</Badge></Td>
            <Td><Money value={e.amount} sign className="font-bold" /></Td>
            <Td><Money value={e.balance_after} /></Td>
          </tr>
        ))}
      </Table>
      {busy && <Spinner />}
      {cursor && !busy && <Btn tone="ghost" className="mt-3 w-full" onClick={() => void load(cursor)}>{t('Load more')}</Btn>}
    </Card>
  )
}

const Statements: React.FC = () => {
  const t = useT()
  const data = useAsync(() => partnerApi.statements(), [])
  return (
    <Card title={t('Period statements')}>
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={[t('Period'), t('Opening'), 'CPA', t('Revshare'), t('Subpartners'), t('Adjustments'), t('Written off'), t('Closing')]} empty={!data.data?.items.length}
          emptyText={t('Statements appear after each settlement period closes.')}>
          {(data.data?.items || []).map((s) => (
            <tr key={s.period_id}>
              <Td className="font-bold">{dateOnly(s.period?.start_date)} – {dateOnly(s.period?.end_date)}</Td>
              <Td><Money value={s.opening_balance} /></Td><Td><Money value={s.cpa_total} /></Td><Td><Money value={s.revshare_total} /></Td>
              <Td><Money value={s.sub_commission_total} /></Td><Td><Money value={s.adjustments_total} /></Td><Td><Money value={s.writeoff} /></Td>
              <Td><Money value={s.closing_balance} className="font-black" /></Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  )
}
