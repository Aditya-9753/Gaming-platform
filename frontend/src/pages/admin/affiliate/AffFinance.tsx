import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Lock, Plus, RotateCcw } from 'lucide-react'
import {
  Badge, Btn, Card, ErrorBox, Field, Modal, Money, Spinner, Table, Tabs, Td, cx, dateOnly, dateTime, inputCls, pct, toastError, useAsync,
} from '../../../components/affiliate/ui'
import { showToast } from '../../../components/common/Toast'
import { usePermission } from '../../../hooks/usePermission'
import { useAuthStore } from '../../../store/auth.store'
import { affAdminApi, saveBlob } from '../../../services/affiliateAdmin.api'
import type { CommissionPlan, Withdrawal } from '../../../types/affiliate.types'
import { ReasonModal } from './AffPartners'

// ============================================================ settlement

export const AffSettlement: React.FC = () => {
  const periods = useAsync(() => affAdminApi.periods(), [])
  const { isSuperAdmin, hasPermission } = usePermission()
  const [selected, setSelected] = useState<number | null>(null)
  const preview = useAsync(() => (selected ? affAdminApi.preview(selected) : Promise.resolve(null)), [selected])
  const statements = useAsync(() => (selected ? affAdminApi.statements(selected) : Promise.resolve(null)), [selected])
  const [confirm, setConfirm] = useState(false)
  const [reopen, setReopen] = useState<null | { title: string; needReason: boolean; run: (r: string) => Promise<void> }>(null)
  const [busy, setBusy] = useState(false)
  const period = periods.data?.items.find((p) => p.id === selected)
  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Settlement periods</h1>
      <p className="text-xs text-slate-400">Closing a period locks its revenue, applies tier rates, moves the period's commission (and CPA whose hold ended) from pending to available,
        pays subpartner shares, applies the carryover policy, writes statements and creates auto-withdrawals.</p>
      <Card>
        {periods.loading && !periods.data ? <Spinner /> : (
          <Table head={['Period', 'Type', 'Status', 'Closed', '']}>
            {(periods.data?.items || []).map((p) => (
              <tr key={p.id} className={cx(selected === p.id && 'bg-brand-blue/10')}>
                <Td className="font-bold">{dateOnly(p.start_date)} – {dateOnly(p.end_date)}</Td><Td>{p.period_type}</Td><Td><Badge status={p.status}>{p.status}</Badge></Td>
                <Td>{dateTime(p.closed_at)}{p.reopened_at && <span className="ml-1 text-[10px] text-amber-300">reopened</span>}</Td>
                <Td><Btn tone="ghost" small onClick={() => setSelected(p.id)}>Open</Btn></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {selected && period && (
        <Card title={`${dateOnly(period.start_date)} – ${dateOnly(period.end_date)}`} actions={
          <>
            {period.status === 'OPEN' && hasPermission('aff:settlement:manage') && (
              <Btn small disabled={period.end_date >= today && !isSuperAdmin()} onClick={() => setConfirm(true)}><Lock className="h-4 w-4" />Close period</Btn>
            )}
            {period.status === 'CLOSED' && isSuperAdmin() && (
              <Btn small tone="ghost" onClick={() => setReopen({ title: 'Reopen period (super admin)', needReason: true, run: async (reason) => {
                await affAdminApi.reopenPeriod(period.id, reason); await periods.reload()
              } })}><RotateCcw className="h-4 w-4" />Reopen</Btn>
            )}
          </>
        }>
          {period.status === 'OPEN' && period.end_date >= today && <p className="mb-3 text-xs text-amber-300">This period has not ended yet; only the super admin can close it early.</p>}
          {preview.data && (
            <>
              <div className="mb-3 grid grid-cols-2 gap-3 text-sm">
                <div><div className="text-[11px] text-slate-500">To settle</div><Money value={preview.data.total_to_settle} className="text-lg font-black" /></div>
                <div><div className="text-[11px] text-slate-500">CPA still on hold</div><Money value={preview.data.held_total} className="text-lg font-black" /></div>
              </div>
              <Table head={['Partner', 'CPA', 'Revshare', 'On hold', 'Rows']} empty={!preview.data.partners.length}>
                {preview.data.partners.map((r) => (
                  <tr key={r.partner_id}><Td><Link to={`/admin/affiliate/partners/${r.partner_id}`} className="font-bold text-blue-300">{r.partner_code}</Link></Td>
                    <Td><Money value={r.cpa} /></Td><Td><Money value={r.revshare} /></Td><Td><Money value={r.held} /></Td><Td>{r.count}</Td></tr>
                ))}
              </Table>
            </>
          )}
          {(statements.data?.items.length ?? 0) > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-xs font-black uppercase text-slate-400">Statements</h4>
              <Table head={['Partner', 'Opening', 'CPA', 'Revshare', 'Sub', 'Adj.', 'Written off', 'Closing']}>
                {statements.data!.items.map((s) => (
                  <tr key={s.partner_id}><Td className="font-bold">{s.partner_code}</Td><Td><Money value={s.opening_balance} /></Td><Td><Money value={s.cpa_total} /></Td>
                    <Td><Money value={s.revshare_total} /></Td><Td><Money value={s.sub_commission_total} /></Td><Td><Money value={s.adjustments_total} /></Td>
                    <Td><Money value={s.writeoff} /></Td><Td><Money value={s.closing_balance} className="font-black" /></Td></tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
      )}
      <Modal open={confirm} title="Close settlement period?" onClose={() => setConfirm(false)}>
        <p className="mb-4 text-sm text-slate-300">Revenue for this period can no longer be changed after closing. This cannot be undone except by the super admin.</p>
        <Btn className="w-full" busy={busy} onClick={async () => {
          setBusy(true)
          try {
            const res = await affAdminApi.closePeriod(selected!)
            showToast({ title: 'Period closed', message: `${res.statements} statements, ${res.auto_withdrawals} auto-withdrawals`, type: 'success' })
            setConfirm(false)
            await periods.reload(); await preview.reload(); await statements.reload()
          } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>Close period</Btn>
      </Modal>
      <ReasonModal action={reopen} onClose={() => setReopen(null)} />
    </div>
  )
}

// ============================================================ withdrawals queue

const QUEUE_TABS = [
  { id: 'PENDING,UNDER_REVIEW', label: 'To review' }, { id: 'APPROVED,PROCESSING', label: 'To pay' },
  { id: 'COMPLETED', label: 'Paid' }, { id: 'REJECTED,CANCELLED,FAILED', label: 'Closed' },
]

export const AffWithdrawals: React.FC = () => {
  const [status, setStatus] = useState(QUEUE_TABS[0].id)
  const data = useAsync(() => affAdminApi.withdrawals({ status }), [status])
  const { hasPermission } = usePermission()
  const canAct = hasPermission('aff:withdrawal:manage')
  const [detail, setDetail] = useState<Withdrawal | null>(null)
  const [act, setAct] = useState<null | { wd: Withdrawal; action: string }>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (wd: Withdrawal, action: string, body: Record<string, unknown> = {}) => {
    setBusy(true)
    try { await affAdminApi.withdrawalAction(wd.id, action, body); setAct(null); setNote(''); await data.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-black">Partner withdrawals</h1>
        {canAct && <Btn tone="ghost" small onClick={async () => { try { saveBlob(await affAdminApi.withdrawalsCsv('APPROVED'), 'partner-payouts-approved.csv') } catch (e) { toastError(e) } }}>
          <Download className="h-4 w-4" />Export approved for payout</Btn>}
      </div>
      <Tabs value={status} onChange={setStatus} tabs={QUEUE_TABS} />
      <Card>
        {data.loading && !data.data ? <Spinner /> : data.error ? <ErrorBox message={data.error} /> : (
          <Table head={['#', 'Partner', 'Requested', 'Amount', 'Net', 'Destination', 'Source', 'Status', '']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((w) => (
              <tr key={w.id}>
                <Td>{w.id}</Td>
                <Td><Link to={`/admin/affiliate/partners/${w.partner_id}`} className="font-bold text-blue-300">{w.partner_code}</Link>{w.payout_frozen && <Badge tone="red">frozen</Badge>}</Td>
                <Td>{dateTime(w.requested_at)}</Td><Td><Money value={w.amount} className="font-bold" /></Td><Td><Money value={w.net_amount} /></Td><Td>{w.destination}</Td>
                <Td>{w.source}</Td><Td><Badge status={w.status}>{w.status}</Badge></Td>
                <Td className="space-x-1">
                  <Btn tone="ghost" small onClick={async () => setDetail(await affAdminApi.withdrawal(w.id))}>History</Btn>
                  {canAct && w.status === 'PENDING' && <Btn tone="ghost" small onClick={() => run(w, 'review')}>Review</Btn>}
                  {canAct && ['PENDING', 'UNDER_REVIEW'].includes(w.status) && <Btn tone="success" small onClick={() => run(w, 'approve')}>Approve</Btn>}
                  {canAct && w.status === 'APPROVED' && <Btn tone="ghost" small onClick={() => run(w, 'processing')}>Processing</Btn>}
                  {canAct && ['APPROVED', 'PROCESSING'].includes(w.status) && <Btn small onClick={() => setAct({ wd: w, action: 'mark-paid' })}>Mark paid</Btn>}
                  {canAct && ['PENDING', 'UNDER_REVIEW', 'APPROVED'].includes(w.status) && <Btn tone="danger" small onClick={() => setAct({ wd: w, action: 'reject' })}>Reject</Btn>}
                  {canAct && w.status === 'PROCESSING' && <Btn tone="danger" small onClick={() => setAct({ wd: w, action: 'fail' })}>Failed</Btn>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Modal open={act !== null} title={act?.action === 'mark-paid' ? 'Mark as paid' : act?.action === 'fail' ? 'Payment failed' : 'Reject withdrawal'} onClose={() => setAct(null)}>
        <div className="space-y-3">
          <p className="text-sm text-slate-300">#{act?.wd.id} · {act?.wd.partner_code} · {act?.wd.net_amount} $ to {act?.wd.destination}</p>
          <Field label={act?.action === 'mark-paid' ? 'Payment reference (from the payout provider)' : 'Reason (shown to the partner)'}>
            <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
          </Field>
          <Btn className="w-full" busy={busy} disabled={note.trim().length < 2} tone={act?.action === 'mark-paid' ? 'primary' : 'danger'}
            onClick={() => act && run(act.wd, act.action, act.action === 'mark-paid' ? { external_payment_reference: note } : { note })}>Confirm</Btn>
        </div>
      </Modal>
      <Modal open={detail !== null} title={`Withdrawal #${detail?.id}`} onClose={() => setDetail(null)}>
        <ol className="space-y-2 text-xs">
          {(detail?.history || []).map((h, i) => (
            <li key={i} className="rounded-lg bg-dark-bg p-2"><b>{h.from || '—'} → {h.to}</b> · {dateTime(h.at)}{h.note && <div className="text-slate-400">{h.note}</div>}</li>
          ))}
        </ol>
        {detail?.external_payment_reference && <p className="mt-3 text-xs">Reference: {detail.external_payment_reference}</p>}
      </Modal>
    </div>
  )
}

// ============================================================ adjustments (maker-checker)

export const AffAdjustments: React.FC = () => {
  const me = useAuthStore((s) => s.user)
  const data = useAsync(() => affAdminApi.adjustments(), [])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ partner_code: '', direction: 'CREDIT', amount: '', reason: '' })
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-black">Manual adjustments</h1><Btn onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Request</Btn></div>
      <p className="text-xs text-slate-400">Maker-checker: a second finance user must approve every credit or debit.</p>
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['#', 'Partner', 'Amount', 'Reason', 'Requested', 'Status', '']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((a) => (
              <tr key={a.id}>
                <Td>{a.id}</Td><Td className="font-bold">{a.partner_code}</Td>
                <Td><Money value={a.direction === 'CREDIT' ? a.amount : `-${a.amount}`} sign className="font-bold" /></Td>
                <Td className="max-w-[240px] truncate">{a.reason}</Td><Td>{dateTime(a.created_at)}</Td><Td><Badge status={a.status}>{a.status}</Badge></Td>
                <Td className="space-x-1">
                  {a.status === 'PENDING' && a.requested_by !== me?.id && (
                    <>
                      <Btn tone="success" small onClick={async () => { try { await affAdminApi.decideAdjustment(a.id, true); void data.reload() } catch (e) { toastError(e) } }}>Approve</Btn>
                      <Btn tone="danger" small onClick={async () => { try { await affAdminApi.decideAdjustment(a.id, false); void data.reload() } catch (e) { toastError(e) } }}>Reject</Btn>
                    </>
                  )}
                  {a.status === 'PENDING' && a.requested_by === me?.id && <span className="text-[11px] text-slate-500">Waiting for a second approver</span>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Modal open={open} title="Request adjustment" onClose={() => setOpen(false)}>
        <div className="space-y-3">
          <Field label="Partner code"><input value={form.partner_code} onChange={(e) => setForm({ ...form, partner_code: e.target.value.toUpperCase() })} className={inputCls} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Direction"><select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })} className={inputCls}><option>CREDIT</option><option>DEBIT</option></select></Field>
            <Field label="Amount $"><input inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className={inputCls} /></Field>
          </div>
          <Field label="Reason"><textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} rows={2} className={cx(inputCls, 'py-2')} /></Field>
          <Btn className="w-full" busy={busy} disabled={!form.partner_code || !Number(form.amount) || form.reason.trim().length < 3} onClick={async () => {
            setBusy(true)
            try {
              const found = await affAdminApi.partners({ q: form.partner_code, limit: 1 })
              const partner = found.items.find((p) => p.partner_code === form.partner_code)
              if (!partner) throw new Error('Partner not found')
              await affAdminApi.requestAdjustment({ partner_id: partner.id, direction: form.direction, amount: form.amount, reason: form.reason })
              setOpen(false); setForm({ partner_code: '', direction: 'CREDIT', amount: '', reason: '' }); void data.reload()
            } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Submit for approval</Btn>
        </div>
      </Modal>
    </div>
  )
}

// ============================================================ wallets

export const AffWallets: React.FC = () => {
  const [negative, setNegative] = useState(false)
  const data = useAsync(() => affAdminApi.wallets({ negative_only: negative }), [negative])
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-black">Partner wallets</h1>
        <div className="flex gap-2">
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={negative} onChange={(e) => setNegative(e.target.checked)} />Negative only</label>
          <Btn tone="ghost" small onClick={async () => {
            try { const r = await affAdminApi.reconcile(); showToast({ title: r.mismatches.length ? `${r.mismatches.length} mismatches — see Risk` : 'Ledger and balances match', type: r.mismatches.length ? 'error' : 'success' }) } catch (e) { toastError(e) }
          }}>Reconcile ledger</Btn>
        </div>
      </div>
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['Partner', 'Available', 'Pending', 'Reserved', 'Status']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((w) => (
              <tr key={w.partner_id}><Td><Link to={`/admin/affiliate/partners/${w.partner_id}`} className="font-bold text-blue-300">{w.partner_code}</Link></Td>
                <Td><Money value={w.available} className="font-bold" /></Td><Td><Money value={w.pending} /></Td><Td><Money value={w.reserved} /></Td>
                <Td>{w.payout_frozen ? <Badge tone="red">payout frozen</Badge> : <Badge status={w.status}>{w.status}</Badge>}</Td></tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}

// ============================================================ plans, deals, FX

const emptyPlan = { name: '', deal_type: 'REVSHARE', default_revshare_rate: '0.5', default_cpa_amount: '0', min_ftd_amount: '0', hold_days: 14, carryover: true, description: '', status: 'ACTIVE' }

export const AffDeals: React.FC = () => {
  const [tab, setTab] = useState('plans')
  const plans = useAsync(() => affAdminApi.plans(), [])
  const deals = useAsync(() => affAdminApi.deals(), [])
  const fx = useAsync(() => affAdminApi.fxRates(), [])
  const { hasPermission } = usePermission()
  const canEdit = hasPermission('aff:deal:manage')
  const [edit, setEdit] = useState<(typeof emptyPlan & { id?: number }) | null>(null)
  const [rate, setRate] = useState({ rate_date: new Date().toISOString().slice(0, 10), currency: 'INR', rate_to_usd: '' })
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Deals & plans</h1>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'plans', label: 'Commission plans' }, { id: 'deals', label: 'Recent deal changes' }, { id: 'fx', label: 'FX rates' }]} />
      {tab === 'plans' && (
        <Card actions={canEdit && <Btn small onClick={() => setEdit({ ...emptyPlan })}><Plus className="h-4 w-4" />New plan</Btn>}>
          <Table head={['Name', 'Type', 'Revshare', 'CPA', 'Min FTD', 'Hold', 'Carryover', 'Status', '']} empty={!plans.data?.items.length}>
            {(plans.data?.items || []).map((p: CommissionPlan) => (
              <tr key={p.id}><Td className="font-bold">{p.name}</Td><Td>{p.deal_type}</Td><Td>{pct(p.default_revshare_rate)}</Td><Td>{p.default_cpa_amount}</Td>
                <Td>{p.min_ftd_amount}</Td><Td>{p.hold_days}d</Td><Td>{p.carryover ? 'on' : 'off'}</Td><Td><Badge status={p.status}>{p.status}</Badge></Td>
                <Td>{canEdit && <Btn tone="ghost" small onClick={() => setEdit({ ...emptyPlan, ...p, description: p.description || '' })}>Edit</Btn>}</Td></tr>
            ))}
          </Table>
        </Card>
      )}
      {tab === 'deals' && (
        <Card>
          <Table head={['Partner', 'From', 'To', 'Type', 'Revshare', 'CPA']} empty={!deals.data?.items.length}>
            {(deals.data?.items || []).map((d) => (
              <tr key={d.id}><Td><Link to={`/admin/affiliate/partners/${d.partner_id}`} className="font-bold text-blue-300">{d.partner_code}</Link></Td>
                <Td>{dateOnly(d.effective_from)}</Td><Td>{d.effective_to ? dateOnly(d.effective_to) : 'current'}</Td><Td>{d.deal_type}</Td><Td>{pct(d.revshare_rate)}</Td><Td>{d.cpa_amount}</Td></tr>
            ))}
          </Table>
        </Card>
      )}
      {tab === 'fx' && (
        <Card title="Daily FX rates to USD">
          <p className="mb-3 text-xs text-slate-400">European Central Bank reference rates are fetched automatically twice a day; deposits and revenue are converted
            with the rate of their day (or the latest before it). Add a rate by hand only for currencies the ECB does not publish.</p>
          {canEdit && <Btn tone="ghost" small className="mb-3" busy={busy} onClick={async () => {
            setBusy(true)
            try { const r = await affAdminApi.syncFx(); showToast({ title: `ECB rates of ${r.date} stored`, message: `${r.currencies} currencies`, type: 'success' }); void fx.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Fetch ECB rates now</Btn>}
          {canEdit && (
            <div className="mb-4 flex flex-wrap gap-2">
              <input type="date" value={rate.rate_date} onChange={(e) => setRate({ ...rate, rate_date: e.target.value })} className={cx(inputCls, 'w-auto')} />
              <input value={rate.currency} maxLength={3} onChange={(e) => setRate({ ...rate, currency: e.target.value.toUpperCase() })} className={cx(inputCls, 'w-24 uppercase')} />
              <input value={rate.rate_to_usd} placeholder="0.0120" onChange={(e) => setRate({ ...rate, rate_to_usd: e.target.value })} className={cx(inputCls, 'w-32')} />
              <Btn busy={busy} disabled={!Number(rate.rate_to_usd)} onClick={async () => { setBusy(true); try { await affAdminApi.setFxRate(rate); void fx.reload() } catch (e) { toastError(e) } finally { setBusy(false) } }}>Save rate</Btn>
            </div>
          )}
          <Table head={['Date', 'Currency', 'Rate to USD']} empty={!fx.data?.items.length}>
            {(fx.data?.items || []).map((r) => <tr key={`${r.rate_date}-${r.currency}`}><Td>{r.rate_date}</Td><Td>{r.currency}</Td><Td>{r.rate_to_usd}</Td></tr>)}
          </Table>
        </Card>
      )}
      <Modal open={edit !== null} title={edit?.id ? 'Edit plan' : 'New plan'} onClose={() => setEdit(null)}>
        {edit && (
          <div className="space-y-3">
            <Field label="Name"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} className={inputCls} /></Field>
            <Field label="Type"><select value={edit.deal_type} onChange={(e) => setEdit({ ...edit, deal_type: e.target.value })} className={inputCls}>{['REVSHARE', 'CPA', 'HYBRID'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Revshare (0.5 = 50%)"><input value={edit.default_revshare_rate} onChange={(e) => setEdit({ ...edit, default_revshare_rate: e.target.value })} className={inputCls} /></Field>
              <Field label="CPA $"><input value={edit.default_cpa_amount} onChange={(e) => setEdit({ ...edit, default_cpa_amount: e.target.value })} className={inputCls} /></Field>
              <Field label="Min FTD $"><input value={edit.min_ftd_amount} onChange={(e) => setEdit({ ...edit, min_ftd_amount: e.target.value })} className={inputCls} /></Field>
              <Field label="Hold days"><input value={edit.hold_days} onChange={(e) => setEdit({ ...edit, hold_days: Number(e.target.value) || 0 })} className={inputCls} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.carryover} onChange={(e) => setEdit({ ...edit, carryover: e.target.checked })} />Carry negative balance over</label>
            <Field label="Status"><select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })} className={inputCls}><option>ACTIVE</option><option>ARCHIVED</option></select></Field>
            <Btn className="w-full" busy={busy} onClick={async () => {
              setBusy(true)
              try {
                const body = { ...edit }
                delete body.id
                if (edit.id) await affAdminApi.updatePlan(edit.id, body); else await affAdminApi.createPlan(body)
                setEdit(null); void plans.reload()
              } catch (e) { toastError(e) } finally { setBusy(false) }
            }}>Save</Btn>
          </div>
        )}
      </Modal>
    </div>
  )
}

