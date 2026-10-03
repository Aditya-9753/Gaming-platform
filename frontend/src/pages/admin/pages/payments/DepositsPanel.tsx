import React, { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import { Modal } from '../../components/Modal'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/Toast'
import { adminPaymentsApi, type AdminDeposit } from '../../../../services/payments.api'
import { formatDateTime, formatPaiseToRupee, rupeeToPaise } from '../../../../utils/formatters'
import { actionFailed, ago, Field, inputCls, StatusPill, Timeline } from './shared'

const FILTERS = [
  { id: 'REVIEW', label: 'Needs review' },
  { id: 'PENDING', label: 'Pending' },
  { id: 'SUCCESS', label: 'Success' },
  { id: 'REJECTED', label: 'Rejected' },
  { id: '', label: 'All' },
]

export const DepositDetail: React.FC<{ id: string; isSuper: boolean; canManage: boolean; onClose: () => void; onChanged: () => void }> = ({ id, isSuper, canManage, onClose, onChanged }) => {
  const [dep, setDep] = useState<AdminDeposit | null>(null)
  const [utr, setUtr] = useState('')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const apply = useCallback((d: AdminDeposit) => {
    setDep(d)
    setUtr(d.utr ?? '')
    setAmount(((d.amount_paise) / 100).toFixed(2))
  }, [])

  useEffect(() => { adminPaymentsApi.deposit(id).then(apply).catch((e) => actionFailed('Could not load deposit', e)) }, [id, apply])

  const run = async (name: string, fn: () => Promise<AdminDeposit>, done: string) => {
    setBusy(name)
    try {
      apply(await fn())
      showToast({ title: done, type: 'success' })
      onChanged()
    } catch (error) { actionFailed(`${name} failed`, error) } finally { setBusy(null) }
  }

  const recheck = async () => {
    setBusy('Check')
    try {
      const d = await adminPaymentsApi.recheck(id)
      apply(d)
      showToast({ title: d.status === 'SUCCESS' ? 'Matched and credited' : 'No matching bank credit yet', type: d.status === 'SUCCESS' ? 'success' : 'info' })
      if (d.status === 'SUCCESS') onChanged()
    } catch (error) { actionFailed('Status check failed', error) } finally { setBusy(null) }
  }

  if (!dep) return <Modal open title="Deposit" onClose={onClose} wide><p className="text-sm text-slate-400">Loading…</p></Modal>
  const open = dep.can_submit_utr
  const act = canManage && dep.can_act
  return (
    <Modal open title={`Deposit ${dep.reference}`} onClose={onClose} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={dep.status} /><span className="text-xs font-bold text-slate-400">{dep.state} · {dep.stage}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field label="Player">{dep.username ?? dep.user_id}</Field>
          <Field label="Requested">{formatPaiseToRupee(dep.amount_paise)}</Field>
          <Field label="Credited">{dep.credited_amount_paise != null ? formatPaiseToRupee(dep.credited_amount_paise) : '-'}</Field>
          <Field label="Player UTR">{dep.utr ?? '-'}</Field>
          <Field label="QR account">{dep.account_label} ({dep.account_owner}) · {dep.payment?.upi_id}</Field>
          <Field label="Verified">{dep.verification_method ? `${dep.verification_method}${dep.verified_by ? ` by ${dep.verified_by}` : ''}` : '-'}</Field>
          <Field label="Created">{formatDateTime(dep.created_at)}</Field>
          <Field label="Expires">{formatDateTime(dep.expires_at)}</Field>
          <Field label="IP">{dep.request_ip ?? '-'}</Field>
        </div>
        {dep.note && <p className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">{dep.note}</p>}
        {dep.bank_credit && (
          <p className="rounded-xl bg-dark-elevated p-3 text-xs text-slate-300">
            Bank credit: UTR <b className="font-mono text-white">{dep.bank_credit.utr}</b> · {formatPaiseToRupee(dep.bank_credit.amount_paise)} · {dep.bank_credit.source}{dep.bank_credit.created_by ? ` by ${dep.bank_credit.created_by}` : ''}
          </p>
        )}

        {open && (dep.candidate_credits?.length ?? 0) > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-black uppercase tracking-wider text-slate-400">Unmatched bank credits that may be this payment</h4>
            {dep.candidate_credits!.map((c) => (
              <div key={c.id} className="flex items-center justify-between rounded-xl bg-dark-elevated px-3 py-2 text-xs">
                <span className="text-slate-200"><b className="font-mono">{c.utr}</b> · {formatPaiseToRupee(c.amount_paise)} · {c.source} · {c.remark ?? ''}</span>
                {act && <Button size="sm" variant="accent" isLoading={busy === 'Assign'} onClick={() => run('Assign', () => adminPaymentsApi.assignCredit(c.id, dep.id), 'Credit assigned — wallet credited')}>Use this</Button>}
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" leftIcon={<RefreshCw className="h-4 w-4" />} isLoading={busy === 'Check'} onClick={recheck} disabled={!open}>Check status</Button>
        </div>

        {open && act && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 rounded-xl border border-emerald-500/30 p-4">
              <h4 className="text-sm font-black text-white">Confirm received (manual)</h4>
              <p className="text-[11px] text-slate-400">Only after you see this money in the bank account behind this QR. Enter the UTR exactly as the bank shows it; it can never be used again.</p>
              <input className={inputCls} placeholder="Bank UTR / reference" value={utr} onChange={(e) => setUtr(e.target.value.toUpperCase())} />
              <input className={inputCls} inputMode="decimal" placeholder="Amount received (₹)" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
              <input className={inputCls} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button size="sm" className="w-full" isLoading={busy === 'Confirm'} disabled={utr.length < 6 || !Number(amount)}
                onClick={() => run('Confirm', () => adminPaymentsApi.confirm(dep.id, { utr, amount_paise: rupeeToPaise(amount), note: note || undefined }), 'Deposit confirmed — wallet credited')}>
                Confirm & credit {amount ? `₹${amount}` : ''}
              </Button>
            </div>
            <div className="space-y-2 rounded-xl border border-rose-500/30 p-4">
              <h4 className="text-sm font-black text-white">Reject</h4>
              <p className="text-[11px] text-slate-400">No money arrived, or the UTR is fake. The player sees the reason.</p>
              <input className={inputCls} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button size="sm" variant="danger" className="w-full" isLoading={busy === 'Reject'} disabled={reason.trim().length < 3}
                onClick={() => run('Reject', () => adminPaymentsApi.rejectDeposit(dep.id, reason), 'Deposit rejected')}>Reject deposit</Button>
            </div>
          </div>
        )}
        {open && !act && <p className="text-xs text-slate-500">This deposit was paid to another admin's QR — only its owner or the super admin can confirm or reject it.</p>}

        {isSuper && dep.status === 'SUCCESS' && (
          <div className="space-y-2 rounded-xl border border-rose-500/30 p-4">
            <h4 className="text-sm font-black text-white">Reverse (bank chargeback)</h4>
            <input className={inputCls} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            <Button size="sm" variant="danger" isLoading={busy === 'Reverse'} disabled={reason.trim().length < 3}
              onClick={() => run('Reverse', () => adminPaymentsApi.reverse(dep.id, reason), 'Deposit reversed')}>Reverse deposit</Button>
            <p className="text-[11px] text-slate-500">Debits the player's available balance; if they already spent it, the wallet is frozen for recovery.</p>
          </div>
        )}

        <div>
          <h4 className="mb-2 text-xs font-black uppercase tracking-wider text-slate-400">Status history</h4>
          <Timeline rows={dep.history} />
        </div>
      </div>
    </Modal>
  )
}

export const DepositsPanel: React.FC<{ isSuper: boolean; canManage: boolean; onChanged: () => void }> = ({ isSuper, canManage, onChanged }) => {
  const [filter, setFilter] = useState('REVIEW')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<AdminDeposit[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await adminPaymentsApi.deposits({ status: filter || undefined, q: search || undefined, page, page_size: 25 })
      setRows(data.items)
      setTotal(data.total)
    } catch (error) { actionFailed('Could not load deposits', error) }
  }, [filter, search, page])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = window.setInterval(() => { void load() }, 15000)
    return () => window.clearInterval(t)
  }, [load])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" onClick={() => { setFilter(f.id); setPage(1) }}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold ${filter === f.id ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'bg-dark-elevated text-slate-400 hover:text-white'}`}>{f.label}</button>
        ))}
        <form className="flex w-full gap-2 sm:ml-auto sm:w-auto" onSubmit={(e) => { e.preventDefault(); setSearch(q); setPage(1) }}>
          <input className={`${inputCls} min-w-0 flex-1 sm:w-56 sm:flex-none`} placeholder="Reference, UTR, deposit id, username" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button size="sm" variant="secondary" type="submit" leftIcon={<Search className="h-4 w-4" />}>Search</Button>
        </form>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-dark-border bg-dark-card">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-dark-border text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="p-3">Reference</th><th className="p-3">Player</th><th className="p-3">Amount</th><th className="p-3">UTR</th><th className="p-3">QR account</th><th className="p-3">Status</th><th className="p-3">Age</th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-slate-500">Nothing here.</td></tr>}
            {rows.map((d) => (
              <tr key={d.id} onClick={() => setOpenId(d.id)} className="cursor-pointer border-b border-dark-border/50 hover:bg-dark-elevated">
                <td className="p-3 font-mono text-white">{d.reference}</td>
                <td className="p-3 text-slate-200">{d.username}</td>
                <td className="p-3 font-bold text-white">{formatPaiseToRupee(d.credited_amount_paise ?? d.amount_paise)}</td>
                <td className="p-3 font-mono text-slate-300">{d.utr ?? '-'}</td>
                <td className="p-3 text-slate-400">{d.account_label} <span className="text-slate-600">({d.account_owner})</span></td>
                <td className="p-3"><StatusPill status={d.status} /><p className="mt-1 text-[10px] text-slate-500">{d.state}</p></td>
                <td className="p-3 text-slate-400">{ago(d.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{total} deposits</span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
          <Button size="sm" variant="ghost" disabled={page * 25 >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      </div>
      {openId && <DepositDetail id={openId} isSuper={isSuper} canManage={canManage} onClose={() => setOpenId(null)} onChanged={() => { void load(); onChanged() }} />}
    </div>
  )
}
