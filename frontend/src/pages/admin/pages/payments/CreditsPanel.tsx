import React, { useCallback, useEffect, useState } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/Toast'
import { adminPaymentsApi, type BankCredit, type CollectionAccount } from '../../../../services/payments.api'
import { formatDateTime, formatPaiseToRupee, rupeeToPaise } from '../../../../utils/formatters'
import { actionFailed, inputCls, StatusPill } from './shared'

/** "UTR, amount in ₹, remark, payer" per line (comma or tab separated); a header row is skipped. */
function parseStatement(text: string) {
  const lines: Array<Record<string, unknown>> = []
  const errors: string[] = []
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim()
    if (!line) return
    const cols = line.split(/\t|,/).map((c) => c.trim())
    const amount = Number(cols[1]?.replace(/[₹\s]/g, ''))
    if (!cols[0] || !Number.isFinite(amount) || amount <= 0) {
      if (i > 0 || !/utr/i.test(line)) errors.push(`Line ${i + 1}: expected "UTR, amount"`)
      return
    }
    lines.push({ utr: cols[0], amount_paise: rupeeToPaise(amount), remark: cols[2] || undefined, payer_name: cols[3] || undefined })
  })
  return { lines, errors }
}

export const CreditsPanel: React.FC<{ canManage: boolean; myId?: string; isSuper: boolean; onChanged: () => void }> = ({ canManage, myId, isSuper, onChanged }) => {
  const [status, setStatus] = useState('UNMATCHED')
  const [rows, setRows] = useState<BankCredit[]>([])
  const [accounts, setAccounts] = useState<CollectionAccount[]>([])
  const [accountId, setAccountId] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setRows((await adminPaymentsApi.credits({ status, page_size: 100 })).items) } catch (error) { actionFailed('Could not load bank credits', error) }
  }, [status])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    adminPaymentsApi.accounts().then((list) => {
      const usable = list.filter((a) => (isSuper || a.owner_id === myId) && a.status !== 'REJECTED')
      setAccounts(usable)
      if (usable[0]) setAccountId(usable[0].id)
    }).catch(() => {})
  }, [isSuper, myId])

  const importLines = async () => {
    const { lines, errors } = parseStatement(text)
    if (errors.length) { showToast({ title: 'Check the statement lines', message: errors.slice(0, 3).join(' · '), type: 'error' }); return }
    if (!lines.length) return
    setBusy(true)
    try {
      const r = await adminPaymentsApi.importCredits(accountId, lines)
      showToast({
        title: `${r.created} imported · ${r.matched} auto-matched`,
        message: [r.duplicates.length ? `${r.duplicates.length} already on file` : '', r.errors.length ? `${r.errors.length} invalid` : ''].filter(Boolean).join(' · ') || undefined,
        type: 'success',
      })
      setText('')
      await load()
      onChanged()
    } catch (error) { actionFailed('Import failed', error) } finally { setBusy(false) }
  }

  const assign = async (credit: BankCredit) => {
    const ref = window.prompt(`Assign UTR ${credit.utr} (${formatPaiseToRupee(credit.amount_paise)}) to which deposit? Enter its reference (RD…)`)
    if (!ref) return
    try {
      const found = await adminPaymentsApi.lookup(ref.trim())
      const dep = found.deposits[0]
      if (!dep) { showToast({ title: 'Deposit not found', type: 'error' }); return }
      await adminPaymentsApi.assignCredit(credit.id, dep.id)
      showToast({ title: `Credited ${dep.reference}`, type: 'success' })
      await load()
      onChanged()
    } catch (error) { actionFailed('Could not assign', error) }
  }

  const ignore = async (credit: BankCredit) => {
    const reason = window.prompt('Why ignore this credit? (e.g. refunded to sender, not a player payment)')
    if (!reason) return
    try { await adminPaymentsApi.ignoreCredit(credit.id, reason); await load() } catch (error) { actionFailed('Could not ignore', error) }
  }

  return (
    <div className="space-y-4">
      {canManage && accounts.length > 0 && (
        <div className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
          <h3 className="text-sm font-black text-white">Import bank statement</h3>
          <p className="text-[11px] text-slate-400">
            Paste credits from your bank / UPI app statement, one per line: <code className="text-slate-300">UTR, amount in ₹, remark, payer</code>.
            Each line is matched automatically by the deposit reference in the remark, the player's UTR, or the unique amount.
          </p>
          <select className={inputCls} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.label} · {a.upi_id}</option>)}
          </select>
          <textarea className={`${inputCls} h-28 font-mono`} placeholder={'412345678901, 500.37, UPI/RDABCD2345XY, Ravi\n412345678902, 1000.12'} value={text} onChange={(e) => setText(e.target.value)} />
          <Button size="sm" variant="accent" leftIcon={<Upload className="h-4 w-4" />} isLoading={busy} onClick={importLines} disabled={!text.trim() || !accountId}>Import & match</Button>
        </div>
      )}
      <div className="flex gap-2">
        {['UNMATCHED', 'MATCHED', 'IGNORED', 'ALL'].map((s) => (
          <button key={s} type="button" onClick={() => setStatus(s)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold ${status === s ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'bg-dark-elevated text-slate-400 hover:text-white'}`}>{s[0] + s.slice(1).toLowerCase()}</button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-2xl border border-dark-border bg-dark-card">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-dark-border text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="p-3">UTR</th><th className="p-3">Amount</th><th className="p-3">Account</th><th className="p-3">Remark / payer</th><th className="p-3">Source</th><th className="p-3">Status</th><th className="p-3" /></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-slate-500">No bank credits.</td></tr>}
            {rows.map((c) => (
              <tr key={c.id} className="border-b border-dark-border/50">
                <td className="p-3 font-mono text-white">{c.utr}</td>
                <td className="p-3 font-bold text-white">{formatPaiseToRupee(c.amount_paise)}</td>
                <td className="p-3 text-slate-400">{c.account_label ?? '—'}</td>
                <td className="p-3 text-slate-400">{c.remark ?? ''}{c.payer_name ? ` · ${c.payer_name}` : ''}</td>
                <td className="p-3 text-slate-400">{c.source}{c.created_by ? ` · ${c.created_by}` : ''}<p className="text-[10px] text-slate-600">{formatDateTime(c.created_at)}</p></td>
                <td className="p-3"><StatusPill status={c.status} /></td>
                <td className="p-3 text-right">
                  {canManage && c.status === 'UNMATCHED' && (
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="secondary" onClick={() => assign(c)}>Assign</Button>
                      <Button size="sm" variant="ghost" onClick={() => ignore(c)}>Ignore</Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
