import React, { useState } from 'react'
import { Pause, Play, Plus, Ticket, Users } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { Badge, Btn, Card, ErrorBox, Field, Modal, Spinner, Table, Td, inputCls } from '../../../components/affiliate/ui'
import { dateTime, toastError, useAsync } from '../../../components/affiliate/helpers'
import { showToast } from '../../../components/common/toastBus'

interface Promo {
  id: string; code: string; amount_paise: number; max_uses: number | null; used_count: number
  expires_at: string | null; is_active: boolean; note: string | null; status: 'ACTIVE' | 'PAUSED' | 'ENDED'; created_at: string | null
}
interface Redemption { user_id: string; username: string; phone: string | null; amount_paise: number; redeemed_at: string | null }

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString('en-IN')}`
const STATUS_TONE = { ACTIVE: 'green', PAUSED: 'slate', ENDED: 'amber' } as const

/** Super admin: bonus promo codes. New accounts get no automatic bonus, so these are the only way a player gets one. */
export const PromoCodes: React.FC = () => {
  const list = useAsync(async () => (await apiClient.get<{ items: Promo[] }>('/admin/promo-codes')).data.items)
  const [creating, setCreating] = useState(false)
  const [viewing, setViewing] = useState<Promo | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const toggle = async (promo: Promo) => {
    setBusyId(promo.id)
    try {
      await apiClient.patch(`/admin/promo-codes/${promo.id}`, { is_active: !promo.is_active })
      await list.reload()
    } catch (e) {
      toastError(e)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Ticket className="h-7 w-7 text-amber-400" />
          <div>
            <h1 className="text-xl font-black text-white">Promo Codes</h1>
            <p className="text-xs text-slate-400">New accounts get no automatic bonus. Players get a bonus only by typing one of these codes
              (at sign-up or in their wallet), and each player can use a code once.</p>
          </div>
        </div>
        <Btn onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New code</Btn>
      </div>

      <Card>
        {list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : !list.data ? <Spinner /> : (
          <Table head={['Code', 'Bonus', 'Used', 'Expires', 'Status', 'Note', '']} empty={list.data.length === 0} emptyText="No promo codes yet. Create one to give players a bonus.">
            {list.data.map((p) => (
              <tr key={p.id}>
                <Td className="font-mono font-black text-white">{p.code}</Td>
                <Td className="font-bold text-emerald-300">{rupees(p.amount_paise)}</Td>
                <Td>{p.used_count}{p.max_uses ? ` / ${p.max_uses}` : ' (no limit)'}</Td>
                <Td>{p.expires_at ? dateTime(p.expires_at) : 'Never'}</Td>
                <Td><Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge></Td>
                <Td className="max-w-[220px] truncate text-slate-400">{p.note || '—'}</Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    <Btn small tone="ghost" onClick={() => setViewing(p)}><Users className="h-3.5 w-3.5" />Who used</Btn>
                    <Btn small tone={p.is_active ? 'ghost' : 'success'} busy={busyId === p.id} onClick={() => void toggle(p)}>
                      {p.is_active ? <><Pause className="h-3.5 w-3.5" />Pause</> : <><Play className="h-3.5 w-3.5" />Resume</>}
                    </Btn>
                  </div>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <CreatePromo open={creating} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); void list.reload() }} />
      <Redemptions promo={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}

const CreatePromo: React.FC<{ open: boolean; onClose: () => void; onCreated: () => void }> = ({ open, onClose, onCreated }) => {
  const [code, setCode] = useState('')
  const [amount, setAmount] = useState('100')
  const [maxUses, setMaxUses] = useState('')
  const [expires, setExpires] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await apiClient.post('/admin/promo-codes', {
        code,
        amount_paise: Math.round(Number(amount) * 100),
        max_uses: maxUses ? Number(maxUses) : null,
        expires_at: expires ? new Date(expires).toISOString() : null,
        note: note || null,
      })
      showToast({ title: 'Promo code created', message: `${code.toUpperCase()} gives ₹${amount} once per player.`, type: 'success' })
      setCode(''); setAmount('100'); setMaxUses(''); setExpires(''); setNote('')
      onCreated()
    } catch (e) {
      toastError(e, 'Not created')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} title="New promo code" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Code" hint="3-32 letters or numbers, e.g. DIWALI100. Players type this.">
          <input className={`${inputCls} font-mono uppercase`} value={code} maxLength={32} required
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))} />
        </Field>
        <Field label="Bonus (₹)" hint="Credited to the player's wallet. Max ₹10,000.">
          <input className={inputCls} type="number" min={1} max={10000} step="1" value={amount} required onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Total uses (optional)" hint="Empty = no limit">
            <input className={inputCls} type="number" min={1} step="1" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
          </Field>
          <Field label="Expires (optional)" hint="Empty = never">
            <input className={inputCls} type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        <Field label="Note (optional)" hint="Only staff see this, e.g. who the code is for">
          <input className={inputCls} value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          Tip: set a total-uses limit. A code shared publicly can be used by everyone who makes an account.
        </p>
        <div className="flex gap-2">
          <Btn tone="ghost" className="flex-1" onClick={onClose}>Cancel</Btn>
          <Btn type="submit" className="flex-1" busy={busy} disabled={code.length < 3 || !(Number(amount) > 0)}>Create</Btn>
        </div>
      </form>
    </Modal>
  )
}

const Redemptions: React.FC<{ promo: Promo | null; onClose: () => void }> = ({ promo, onClose }) => {
  const rows = useAsync(async () => (promo ? (await apiClient.get<{ items: Redemption[] }>(`/admin/promo-codes/${promo.id}/redemptions`)).data.items : []), [promo?.id])
  return (
    <Modal open={promo !== null} title={`Who used ${promo?.code ?? ''}`} onClose={onClose} wide>
      {rows.error ? <ErrorBox message={rows.error} onRetry={rows.reload} /> : !rows.data ? <Spinner /> : (
        <Table head={['Player', 'Mobile', 'Bonus', 'When']} empty={rows.data.length === 0} emptyText="Nobody has used this code yet.">
          {rows.data.map((r) => (
            <tr key={r.user_id}>
              <Td className="font-bold text-white">{r.username}</Td>
              <Td>{r.phone || '—'}</Td>
              <Td className="text-emerald-300">{rupees(r.amount_paise)}</Td>
              <Td>{dateTime(r.redeemed_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Modal>
  )
}
