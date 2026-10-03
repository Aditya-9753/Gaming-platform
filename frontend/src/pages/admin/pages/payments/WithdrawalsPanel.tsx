import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Eye, Search } from 'lucide-react'
import { Modal } from '../../components/Modal'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/Toast'
import { adminPaymentsApi, type AdminWithdrawal } from '../../../../services/payments.api'
import { useAuthStore } from '../../../../store/auth.store'
import { formatDateTime, formatPaiseToRupee } from '../../../../utils/formatters'
import { actionFailed, ago, Field, inputCls, StatusPill, Timeline } from './shared'

const FLAG_LABEL: Record<string, string> = {
  first_withdrawal: 'First withdrawal',
  new_payout_account: 'New payout account (< 72 h)',
  shared_payout_account: 'Payout account used by other players',
  deposit_then_withdraw: 'Withdrawing right after a deposit',
  high_value: 'High value — maker-checker',
  velocity_24h: 'Many withdrawals in 24 h',
  bonus_heavy: 'Bonus credits exceed real deposits',
}

const riskTone = (score: number) => (score >= 50 ? 'text-rose-400' : score >= 25 ? 'text-amber-300' : 'text-emerald-400')

export const WithdrawalDetail: React.FC<{ id: string; isSuper: boolean; canManage: boolean; onClose: () => void; onChanged: () => void }> = ({ id, isSuper, canManage, onClose, onChanged }) => {
  const me = useAuthStore((s) => s.user?.id)
  const [wd, setWd] = useState<AdminWithdrawal | null>(null)
  const [details, setDetails] = useState<Record<string, string | null> | null>(null)
  const [utr, setUtr] = useState('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => { adminPaymentsApi.withdrawal(id).then(setWd).catch((e) => actionFailed('Could not load withdrawal', e)) }, [id])

  const run = async (name: string, fn: () => Promise<AdminWithdrawal>, done: string) => {
    setBusy(name)
    try {
      setWd(await fn())
      showToast({ title: done, type: 'success' })
      onChanged()
    } catch (error) {
      actionFailed(`${name} failed`, error)
      adminPaymentsApi.withdrawal(id).then(setWd).catch(() => {})
    } finally { setBusy(null) }
  }

  const reveal = async () => {
    setBusy('Reveal')
    try { setDetails(await adminPaymentsApi.payoutDetails(id)) } catch (error) { actionFailed('Could not show details', error) } finally { setBusy(null) }
  }

  if (!wd) return <Modal open title="Withdrawal" onClose={onClose} wide><p className="text-sm text-slate-400">Loading…</p></Modal>
  const open = wd.state === 'AWAITING_APPROVAL' || wd.state === 'PAYOUT_INITIATED'
  const needsMaker = wd.high_value && wd.state === 'AWAITING_APPROVAL'
  const iAmMaker = wd.initiated_by_id === me
  const flags = Object.entries(wd.risk_flags ?? {})
  return (
    <Modal open title={`Withdrawal · ${formatPaiseToRupee(wd.amount_paise)}`} onClose={onClose} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={wd.status} /><span className="text-xs font-bold text-slate-400">{wd.state} · {wd.stage}</span>
          <span className={`ml-auto text-sm font-black ${riskTone(wd.risk_score)}`}>Risk {wd.risk_score}/100</span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field label="Player">{wd.username ?? wd.user_id}</Field>
          <Field label="Pay to">{wd.payout_to}</Field>
          <Field label="Requested">{formatDateTime(wd.created_at)} ({ago(wd.created_at)})</Field>
          <Field label="Initiated">{wd.initiated_by ? `${wd.initiated_by} · ${formatDateTime(wd.initiated_at ?? '')}` : '-'}</Field>
          <Field label="Completed / rejected by">{wd.completed_by ?? wd.rejected_by ?? '-'}</Field>
          <Field label="Payout UTR">{wd.payout_reference ?? '-'}</Field>
          {wd.player && (
            <>
              <Field label="Lifetime deposited">{formatPaiseToRupee(wd.player.lifetime_deposited_paise)} ({wd.player.deposit_count}×)</Field>
              <Field label="Lifetime withdrawn">{formatPaiseToRupee(wd.player.lifetime_withdrawn_paise)}</Field>
              <Field label="Wagered since first deposit">{formatPaiseToRupee(wd.player.wagered)}</Field>
            </>
          )}
          <Field label="IP">{wd.request_ip ?? '-'}</Field>
        </div>
        {flags.length > 0 && (
          <ul className="space-y-1 rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">
            {flags.map(([k, v]) => <li key={k} className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" />{FLAG_LABEL[k] ?? k}{typeof v === 'number' ? ` (${v})` : ''}</li>)}
          </ul>
        )}
        {wd.reject_reason && <p className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-3 text-xs text-rose-200">Rejected: {wd.reject_reason}</p>}
        {wd.admin_note && <p className="text-xs text-slate-400">Note: {wd.admin_note}</p>}

        {isSuper && open && (
          <div className="rounded-xl bg-dark-elevated p-3">
            {details ? (
              <div className="grid gap-2 font-mono text-sm text-white sm:grid-cols-2">
                {Object.entries(details).filter(([, v]) => v).map(([k, v]) => <Field key={k} label={k.replace('_', ' ')}>{v}</Field>)}
              </div>
            ) : (
              <Button size="sm" variant="secondary" leftIcon={<Eye className="h-4 w-4" />} isLoading={busy === 'Reveal'} onClick={reveal}>Show full bank details (audited)</Button>
            )}
          </div>
        )}

        {open && canManage && (
          <div className="grid gap-4 md:grid-cols-2">
            {wd.state === 'AWAITING_APPROVAL' && (
              <div className="space-y-2 rounded-xl border border-purple-500/30 p-4">
                <h4 className="text-sm font-black text-white">Mark payout initiated {wd.high_value && <span className="text-[10px] text-amber-300">(maker step)</span>}</h4>
                <p className="text-[11px] text-slate-400">Records that the bank transfer has been started. For high-value requests a different super admin then confirms.</p>
                <input className={inputCls} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button size="sm" variant="accent" isLoading={busy === 'Initiate'} onClick={() => run('Initiate', () => adminPaymentsApi.initiate(wd.id, note, wd.version), 'Marked as payout initiated')}>Payout initiated</Button>
              </div>
            )}
            {isSuper && (
              <div className="space-y-2 rounded-xl border border-emerald-500/30 p-4">
                <h4 className="text-sm font-black text-white">Complete</h4>
                <p className="text-[11px] text-slate-400">Send the money first, then enter the bank payout UTR. It must be unique.</p>
                {needsMaker && <p className="text-[11px] font-bold text-amber-300">High value: another admin must mark "payout initiated" first.</p>}
                {wd.high_value && iAmMaker && <p className="text-[11px] font-bold text-amber-300">You initiated this payout — another super admin must complete it.</p>}
                <input className={inputCls} placeholder="Bank payout UTR" value={utr} onChange={(e) => setUtr(e.target.value.toUpperCase())} />
                <Button size="sm" className="w-full" isLoading={busy === 'Complete'} disabled={utr.length < 6 || needsMaker || (wd.high_value && iAmMaker)}
                  onClick={() => run('Complete', () => adminPaymentsApi.complete(wd.id, utr, wd.version), 'Withdrawal completed')}>Mark COMPLETED</Button>
              </div>
            )}
            {isSuper && (
              <div className="space-y-2 rounded-xl border border-rose-500/30 p-4">
                <h4 className="text-sm font-black text-white">Reject</h4>
                <p className="text-[11px] text-slate-400">The held amount goes back to the player's wallet. They see the reason.</p>
                <input className={inputCls} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                <Button size="sm" variant="danger" className="w-full" isLoading={busy === 'Reject'} disabled={reason.trim().length < 3}
                  onClick={() => run('Reject', () => adminPaymentsApi.rejectWithdrawal(wd.id, reason, wd.version), 'Withdrawal rejected, funds returned')}>Reject & refund</Button>
              </div>
            )}
          </div>
        )}
        {open && !isSuper && <p className="text-xs text-slate-500">Only the super admin can complete or reject withdrawals.</p>}

        <div>
          <h4 className="mb-2 text-xs font-black uppercase tracking-wider text-slate-400">Status history</h4>
          <Timeline rows={wd.history} />
        </div>
      </div>
    </Modal>
  )
}

export const WithdrawalsPanel: React.FC<{ isSuper: boolean; canManage: boolean; onChanged: () => void }> = ({ isSuper, canManage, onChanged }) => {
  const [filter, setFilter] = useState('PENDING')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<AdminWithdrawal[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await adminPaymentsApi.withdrawals({ status: filter, q: search || undefined, page, page_size: 25 })
      setRows(data.items)
      setTotal(data.total)
    } catch (error) { actionFailed('Could not load withdrawals', error) }
  }, [filter, search, page])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = window.setInterval(() => { void load() }, 15000)
    return () => window.clearInterval(t)
  }, [load])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {['PENDING', 'COMPLETED', 'REJECTED', 'ALL'].map((f) => (
          <button key={f} type="button" onClick={() => { setFilter(f); setPage(1) }}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold ${filter === f ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'bg-dark-elevated text-slate-400 hover:text-white'}`}>{f === 'ALL' ? 'All' : f[0] + f.slice(1).toLowerCase()}</button>
        ))}
        <form className="flex w-full gap-2 sm:ml-auto sm:w-auto" onSubmit={(e) => { e.preventDefault(); setSearch(q); setPage(1) }}>
          <input className={`${inputCls} min-w-0 flex-1 sm:w-56 sm:flex-none`} placeholder="Withdrawal id, payout UTR, username" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button size="sm" variant="secondary" type="submit" leftIcon={<Search className="h-4 w-4" />}>Search</Button>
        </form>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-dark-border bg-dark-card">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-dark-border text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="p-3">Player</th><th className="p-3">Amount</th><th className="p-3">Pay to</th><th className="p-3">Risk</th><th className="p-3">Status</th><th className="p-3">Waiting</th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-slate-500">Nothing here.</td></tr>}
            {rows.map((w) => (
              <tr key={w.id} onClick={() => setOpenId(w.id)} className="cursor-pointer border-b border-dark-border/50 hover:bg-dark-elevated">
                <td className="p-3 text-slate-200">{w.username}</td>
                <td className="p-3 font-bold text-white">{formatPaiseToRupee(w.amount_paise)}{w.high_value && <span className="ml-1 text-[10px] text-amber-300">HV</span>}</td>
                <td className="p-3 text-slate-400">{w.payout_to}</td>
                <td className={`p-3 font-black ${riskTone(w.risk_score)}`}>{w.risk_score}</td>
                <td className="p-3"><StatusPill status={w.status} /><p className="mt-1 text-[10px] text-slate-500">{w.state}</p></td>
                <td className="p-3 text-slate-400">{ago(w.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{total} withdrawals</span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
          <Button size="sm" variant="ghost" disabled={page * 25 >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      </div>
      {openId && <WithdrawalDetail id={openId} isSuper={isSuper} canManage={canManage} onClose={() => setOpenId(null)} onChanged={() => { void load(); onChanged() }} />}
    </div>
  )
}
