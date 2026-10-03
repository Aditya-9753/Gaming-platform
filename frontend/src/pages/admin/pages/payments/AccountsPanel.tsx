import React, { useCallback, useEffect, useState } from 'react'
import { Check, ImagePlus, Plus, X } from 'lucide-react'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/Toast'
import { adminPaymentsApi, type CollectionAccount } from '../../../../services/payments.api'
import { formatPaiseToRupee, rupeeToPaise } from '../../../../utils/formatters'
import { actionFailed, inputCls, StatusPill } from './shared'

const MAX_IMAGE_BYTES = 400 * 1024

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { reject(new Error('Use a PNG, JPEG or WebP image')); return }
    if (file.size > MAX_IMAGE_BYTES) { reject(new Error('Image must be under 400 KB')); return }
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('Could not read the image'))
    reader.readAsDataURL(file)
  })
}

const empty = { label: '', upi_id: '', payee_name: '', bank_name: '', min: '', max: '', daily: '', qr_image: '' }

const AccountForm: React.FC<{ onSaved: () => void; isSuper: boolean }> = ({ onSaved, isSuper }) => {
  const [form, setForm] = useState(empty)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof empty) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const pick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try { const qr = await readImage(file); setForm((f) => ({ ...f, qr_image: qr })) } catch (error) {
      showToast({ title: 'QR image not accepted', message: (error as Error).message, type: 'error' })
    }
  }

  const save = async () => {
    setBusy(true)
    try {
      await adminPaymentsApi.createAccount({
        label: form.label, upi_id: form.upi_id, payee_name: form.payee_name, bank_name: form.bank_name || undefined,
        qr_image: form.qr_image || undefined, min_amount_paise: rupeeToPaise(form.min || 0),
        max_amount_paise: rupeeToPaise(form.max || 0), daily_limit_paise: rupeeToPaise(form.daily || 0),
      })
      showToast({ title: 'QR account added', message: isSuper ? 'It is live now.' : 'The super admin must approve it before players see it.', type: 'success' })
      setForm(empty)
      onSaved()
    } catch (error) { actionFailed('Could not add account', error) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-dashed border-purple-500/40 bg-dark-card p-5">
      <h3 className="text-sm font-black text-white">Add my UPI QR</h3>
      <div className="grid gap-2 md:grid-cols-3">
        <input className={inputCls} placeholder="Label (e.g. My PhonePe)" value={form.label} onChange={set('label')} />
        <input className={inputCls} placeholder="UPI ID (name@okaxis)" value={form.upi_id} onChange={set('upi_id')} />
        <input className={inputCls} placeholder="Payee name (as on the UPI ID)" value={form.payee_name} onChange={set('payee_name')} />
        <input className={inputCls} placeholder="Bank name (optional)" value={form.bank_name} onChange={set('bank_name')} />
        <input className={inputCls} inputMode="decimal" placeholder="Min per deposit ₹ (0 = none)" value={form.min} onChange={set('min')} />
        <input className={inputCls} inputMode="decimal" placeholder="Max per deposit ₹ (0 = none)" value={form.max} onChange={set('max')} />
        <input className={inputCls} inputMode="decimal" placeholder="Daily limit ₹ (0 = none)" value={form.daily} onChange={set('daily')} />
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-xs text-slate-300 hover:border-purple-500">
          <ImagePlus className="h-4 w-4" />{form.qr_image ? 'QR image attached' : 'Upload QR image (optional)'}
          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={pick} />
        </label>
      </div>
      <p className="text-[11px] text-slate-500">Players get a QR generated from this UPI ID with the exact amount and their reference filled in. An uploaded QR image is shown as an alternative. Changing the UPI ID, payee or image later sends the account back for approval.</p>
      <Button size="sm" variant="accent" leftIcon={<Plus className="h-4 w-4" />} isLoading={busy} onClick={save} disabled={!form.label || !form.upi_id || !form.payee_name}>Add QR account</Button>
    </div>
  )
}

export const AccountsPanel: React.FC<{ isSuper: boolean; canManage: boolean; myId?: string; onChanged: () => void }> = ({ isSuper, canManage, myId, onChanged }) => {
  const [accounts, setAccounts] = useState<CollectionAccount[]>([])
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setAccounts(await adminPaymentsApi.accounts()) } catch (error) { actionFailed('Could not load accounts', error) }
  }, [])
  useEffect(() => { void load() }, [load])

  const act = async (id: string, fn: () => Promise<unknown>, done: string) => {
    setBusy(id)
    try { await fn(); showToast({ title: done, type: 'success' }); await load(); onChanged() } catch (error) { actionFailed('Action failed', error) } finally { setBusy(null) }
  }

  const showImage = async (id: string) => {
    try { setPreview((await adminPaymentsApi.account(id)).qr_image) } catch (error) { actionFailed('Could not load image', error) }
  }

  return (
    <div className="space-y-4">
      {canManage && <AccountForm onSaved={load} isSuper={isSuper} />}
      <div className="grid gap-3 lg:grid-cols-2">
        {accounts.length === 0 && <p className="text-sm text-slate-500">No QR accounts yet.</p>}
        {accounts.map((a) => {
          const mine = a.owner_id === myId
          const canEdit = canManage && (isSuper || mine)
          return (
            <div key={a.id} className={`space-y-3 rounded-2xl border bg-dark-card p-4 ${a.status === 'ACTIVE' ? 'border-emerald-500/30' : 'border-dark-border'}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-black text-white">{a.label}</p>
                  <p className="font-mono text-xs text-slate-300">{a.upi_id}</p>
                  <p className="text-[11px] text-slate-500">{a.payee_name}{a.bank_name ? ` · ${a.bank_name}` : ''} · owner {a.owner}{mine ? ' (you)' : ''}</p>
                </div>
                <StatusPill status={a.status} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div><p className="text-slate-500">Received today</p><p className="font-bold text-white">{formatPaiseToRupee(a.received_today_paise, false)}</p></div>
                <div><p className="text-slate-500">Open requests</p><p className="font-bold text-white">{formatPaiseToRupee(a.open_paise, false)}</p></div>
                <div><p className="text-slate-500">Daily limit</p><p className="font-bold text-white">{a.daily_limit_paise ? formatPaiseToRupee(a.daily_limit_paise, false) : 'None'}</p></div>
              </div>
              {a.review_note && <p className="text-[11px] text-slate-400">Review note: {a.review_note}</p>}
              <div className="flex flex-wrap gap-2">
                {a.has_qr_image && <Button size="sm" variant="ghost" onClick={() => showImage(a.id)}>View QR image</Button>}
                {isSuper && a.status === 'PENDING_APPROVAL' && (
                  <>
                    <Button size="sm" leftIcon={<Check className="h-4 w-4" />} isLoading={busy === a.id} onClick={() => act(a.id, () => adminPaymentsApi.reviewAccount(a.id, true), 'Account approved — now live')}>Approve</Button>
                    <Button size="sm" variant="danger" leftIcon={<X className="h-4 w-4" />} onClick={() => {
                      const note = window.prompt('Reason for rejecting this account?') ?? ''
                      if (note) void act(a.id, () => adminPaymentsApi.reviewAccount(a.id, false, note), 'Account rejected')
                    }}>Reject</Button>
                  </>
                )}
                {canEdit && a.status === 'ACTIVE' && <Button size="sm" variant="secondary" isLoading={busy === a.id} onClick={() => act(a.id, () => adminPaymentsApi.updateAccount(a.id, { active: false }), 'Account disabled')}>Disable</Button>}
                {canEdit && a.status === 'DISABLED' && <Button size="sm" variant="secondary" isLoading={busy === a.id} onClick={() => act(a.id, () => adminPaymentsApi.updateAccount(a.id, { active: true }), 'Account enabled')}>Enable</Button>}
                {canEdit && a.status !== 'REJECTED' && (
                  <Button size="sm" variant="ghost" onClick={() => {
                    const daily = window.prompt('New daily limit in ₹ (0 = no limit)', String(a.daily_limit_paise / 100))
                    if (daily !== null) void act(a.id, () => adminPaymentsApi.updateAccount(a.id, { daily_limit_paise: rupeeToPaise(daily || 0) }), 'Daily limit saved')
                  }}>Daily limit</Button>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {preview && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4" onClick={() => setPreview(null)}>
          <img src={preview} alt="Uploaded QR" className="max-h-[80vh] rounded-xl bg-white p-2" />
        </div>
      )}
    </div>
  )
}
