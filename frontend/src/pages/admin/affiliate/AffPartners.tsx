import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Eye, Plus, Search, Snowflake } from 'lucide-react'
import {
  Badge, Btn, Card, CopyButton, Empty, ErrorBox, Field, Modal, Money, Spinner, Table, Tabs, Td, cx, dateOnly, dateTime, inputCls, pct,
  toastError, useAsync,
} from '../../../components/affiliate/ui'
import { showToast } from '../../../components/common/Toast'
import { usePermission } from '../../../hooks/usePermission'
import { affAdminApi } from '../../../services/affiliateAdmin.api'
import type { LedgerEntry } from '../../../types/affiliate.types'

const STATUS_TABS = [{ id: '', label: 'All' }, { id: 'PENDING', label: 'Pending' }, { id: 'ACTIVE', label: 'Active' }, { id: 'SUSPENDED', label: 'Suspended' }, { id: 'BLOCKED', label: 'Blocked' }]

export const dealText = (d?: { deal_type: string; revshare_rate: string; cpa_amount: string } | null) =>
  !d ? '—' : `${d.deal_type}${Number(d.revshare_rate) > 0 && d.deal_type !== 'CPA' ? ` ${pct(d.revshare_rate)}` : ''}${Number(d.cpa_amount) > 0 ? ` · CPA ${d.cpa_amount}$` : ''}`

export const AffPartners: React.FC<{ subpartnersOnly?: boolean }> = ({ subpartnersOnly }) => {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || ''
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const { hasPermission } = usePermission()
  const data = useAsync(() => affAdminApi.partners({ status: status || undefined, q: search || undefined, subpartners_only: subpartnersOnly, limit: 50, offset: page * 50 }),
    [status, search, page, subpartnersOnly])
  const [createOpen, setCreateOpen] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-black">{subpartnersOnly ? 'Subpartners' : 'Partners'}</h1>
        {hasPermission('aff:partner:manage') && !subpartnersOnly && <Btn onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" />Create partner</Btn>}
      </div>
      {!subpartnersOnly && <Tabs value={status} onChange={(id) => { setPage(0); setParams(id ? { status: id } : {}) }} tabs={STATUS_TABS} />}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setPage(0); setSearch(q) }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Email or partner code" className={inputCls} />
        <Btn type="submit"><Search className="h-4 w-4" /></Btn>
      </form>
      <Card>
        {data.loading && !data.data ? <Spinner /> : data.error ? <ErrorBox message={data.error} onRetry={data.reload} /> : (
          <>
            <Table head={['Code', 'Email', 'Status', 'Deal', 'Available', 'Pending', 'Joined']} empty={!data.data?.items.length}>
              {(data.data?.items || []).map((p) => (
                <tr key={p.id}>
                  <Td><Link to={`/admin/affiliate/partners/${p.id}`} className="font-black text-blue-300 hover:underline">{p.partner_code}</Link>
                    {p.parent_partner_id && <span className="ml-1 text-[10px] text-slate-500">sub</span>}
                    {p.payout_frozen && <Snowflake className="ml-1 inline h-3 w-3 text-cyan-300" />}</Td>
                  <Td>{p.email}</Td><Td><Badge status={p.status}>{p.status}</Badge></Td><Td>{dealText(p.deal)}</Td>
                  <Td><Money value={p.wallet?.available} /></Td><Td><Money value={p.wallet?.pending} /></Td><Td>{dateOnly(p.created_at)}</Td>
                </tr>
              ))}
            </Table>
            <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
              <span>{data.data?.total ?? 0} partners</span>
              <div className="flex gap-2">
                <Btn tone="ghost" small disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</Btn>
                <Btn tone="ghost" small disabled={(page + 1) * 50 >= (data.data?.total || 0)} onClick={() => setPage(page + 1)}>Next</Btn>
              </div>
            </div>
          </>
        )}
      </Card>
      <CreatePartnerModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => void data.reload()} />
    </div>
  )
}

const CreatePartnerModal: React.FC<{ open: boolean; onClose: () => void; onCreated: () => void }> = ({ open, onClose, onCreated }) => {
  const { hasPermission } = usePermission()
  const navigate = useNavigate()
  const plans = useAsync(() => affAdminApi.plans(), [open])
  const staff = useAsync(() => affAdminApi.staff(), [open])
  const [form, setForm] = useState({ email: '', password: '', first_name: '', last_name: '', telegram: '', plan_id: '', manager_id: '', parent_partner_id: '', timezone: 'Asia/Kolkata' })
  const [created, setCreated] = useState<{ id: number; code: string; query?: string; redirect?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const close = () => { setCreated(null); onClose() }
  return (
    <Modal open={open} title={created ? 'Partner created' : 'Create partner'} onClose={close}>
      {created ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-300">Partner <b>{created.code}</b> is active. Their Default tracking link is ready:</p>
          {[created.query, created.redirect].filter(Boolean).map((url) => (
            <div key={url} className="flex items-center gap-2"><code className="min-w-0 flex-1 truncate rounded-lg bg-dark-elevated px-2 py-2 text-xs">{url}</code><CopyButton text={url!} /></div>
          ))}
          <Btn className="w-full" onClick={() => { close(); navigate(`/admin/affiliate/partners/${created.id}`) }}>Open partner</Btn>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputCls} /></Field>
          <Field label="Password (optional)" hint="Leave empty to email the partner a set-password link">
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className={inputCls} autoComplete="new-password" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name"><input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className={inputCls} /></Field>
            <Field label="Last name"><input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className={inputCls} /></Field>
          </div>
          <Field label="Telegram"><input value={form.telegram} onChange={(e) => setForm({ ...form, telegram: e.target.value })} className={inputCls} /></Field>
          <Field label="Deal (plan)">
            <select value={form.plan_id} onChange={(e) => setForm({ ...form, plan_id: e.target.value })} className={inputCls}>
              <option value="">Default plan</option>
              {(plans.data?.items || []).filter((p) => p.status === 'ACTIVE').map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Manager">
            <select value={form.manager_id} onChange={(e) => setForm({ ...form, manager_id: e.target.value })} className={inputCls}>
              <option value="">—</option>
              {(staff.data?.items || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Master partner id (optional)"><input inputMode="numeric" value={form.parent_partner_id} onChange={(e) => setForm({ ...form, parent_partner_id: e.target.value.replace(/\D/g, '') })} className={inputCls} /></Field>
            <Field label="Timezone"><input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} className={inputCls} /></Field>
          </div>
          {!hasPermission('aff:deal:manage') && <p className="text-[11px] text-slate-500">Custom rates are set by finance after creation.</p>}
          <Btn className="w-full" busy={busy} disabled={!form.email} onClick={async () => {
            setBusy(true)
            try {
              const res = await affAdminApi.createPartner({
                email: form.email, password: form.password || undefined, timezone: form.timezone || undefined,
                manager_id: form.manager_id || undefined, parent_partner_id: form.parent_partner_id ? Number(form.parent_partner_id) : undefined,
                profile: { first_name: form.first_name || undefined, last_name: form.last_name || undefined, telegram: form.telegram || undefined },
                deal: form.plan_id ? { plan_id: Number(form.plan_id) } : {},
              })
              setCreated({ id: res.partner.id, code: res.partner.partner_code, query: res.default_link.urls.query, redirect: res.default_link.urls.redirect })
              onCreated()
            } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Create partner + Default link</Btn>
        </div>
      )}
    </Modal>
  )
}

export const AffPartnerDetail: React.FC = () => {
  const id = Number(useParams().id)
  const { hasPermission, isSuperAdmin } = usePermission()
  const data = useAsync(() => affAdminApi.partner(id), [id])
  const [tab, setTab] = useState('overview')
  const [dealOpen, setDealOpen] = useState(false)
  const [action, setAction] = useState<null | { title: string; needReason: boolean; run: (reason: string) => Promise<void> }>(null)
  if (data.loading && !data.data) return <Spinner />
  if (data.error) return <ErrorBox message={data.error} onRetry={data.reload} />
  const d = data.data!
  const p = d.partner
  const can = (perm: string) => isSuperAdmin() || hasPermission(perm)
  const status = (next: string, title: string) => setAction({ title, needReason: next !== 'ACTIVE', run: async (reason) => {
    await affAdminApi.setStatus(p.id, next, reason || undefined); await data.reload()
  } })

  return (
    <div className="space-y-4">
      <Link to="/admin/affiliate/partners" className="text-xs text-blue-300">← Partners</Link>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-black">{p.partner_code}</h1>
        <Badge status={p.status}>{p.status}</Badge>
        {p.payout_frozen && <Badge tone="red">Payouts frozen</Badge>}
        {p.parent_partner_id && <Link to={`/admin/affiliate/partners/${p.parent_partner_id}`}><Badge tone="purple">Sub of #{p.parent_partner_id}</Badge></Link>}
        <span className="text-sm text-slate-400">{p.email} · {d.name || '—'}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {can('aff:impersonate') && (
            <Btn tone="ghost" small onClick={async () => {
              try {
                const res = await affAdminApi.impersonate(p.id)
                window.open(`/partner/impersonate#token=${encodeURIComponent(res.access_token)}`, '_blank', 'noopener')
              } catch (e) { toastError(e) }
            }}><Eye className="h-4 w-4" />View as partner</Btn>
          )}
          {can('aff:partner:manage') && p.status === 'PENDING' && <Btn small tone="success" onClick={() => status('ACTIVE', 'Approve partner')}>Approve</Btn>}
          {can('aff:partner:manage') && p.status === 'ACTIVE' && <Btn small tone="danger" onClick={() => status('SUSPENDED', 'Suspend partner')}>Suspend</Btn>}
          {can('aff:partner:manage') && (p.status === 'SUSPENDED' || p.status === 'BLOCKED') && <Btn small onClick={() => status('ACTIVE', 'Reactivate partner')}>Reactivate</Btn>}
          {can('aff:partner:manage') && p.status !== 'BLOCKED' && <Btn small tone="ghost" onClick={() => status('BLOCKED', 'Block partner')}>Block</Btn>}
          {can('aff:risk:manage') && (
            <Btn small tone="ghost" onClick={() => setAction({ title: p.payout_frozen ? 'Unfreeze payouts' : 'Freeze payouts', needReason: true, run: async (reason) => {
              await affAdminApi.freeze(p.id, !p.payout_frozen, reason); await data.reload()
            } })}><Snowflake className="h-4 w-4" />{p.payout_frozen ? 'Unfreeze' : 'Freeze'}</Btn>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[['Available', d.wallet.available], ['Pending', d.wallet.pending], ['Reserved', d.wallet.reserved], ['Income (all time)', String(d.stats.income ?? '0')]].map(([label, value]) => (
          <Card key={label}><div className="text-[10px] uppercase text-slate-400">{label}</div><Money value={value} className="text-lg font-black" /></Card>
        ))}
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'overview', label: 'Overview' }, { id: 'links', label: 'Links' }, { id: 'deal', label: 'Deal' },
        { id: 'ledger', label: 'Ledger' }, { id: 'withdrawals', label: 'Withdrawals' }, { id: 'activity', label: 'Players' }]} />

      {tab === 'overview' && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="Statistics (all time)">
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {[['Clicks', d.stats.transitions], ['Registrations', d.stats.registrations], ['FTD', d.stats.first_deposits], ['Deposits', d.stats.deposit_count],
                ['Clicks / reg', d.stats.ratio_registrations ?? '—'], ['EPC', d.stats.cost_transition ?? '—'], ['NGR', d.stats.ngr], ['Avg player income', d.stats.avg_player_income ?? '—']].map(([k, v]) => (
                <div key={String(k)}><dt className="text-[11px] text-slate-500">{k}</dt><dd className="font-bold">{String(v)}</dd></div>
              ))}
            </dl>
          </Card>
          <PartnerSettingsCard d={d} onSaved={() => void data.reload()} canEdit={can('aff:partner:manage')} />
          <Card title="Profile">
            <dl className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(d.profile).filter(([, v]) => v).map(([k, v]) => <div key={k}><dt className="text-slate-500">{k.replace('_', ' ')}</dt><dd className="break-words">{v}</dd></div>)}
              <div><dt className="text-slate-500">email verified</dt><dd>{d.email_verified ? 'yes' : 'no'}</dd></div>
              <div><dt className="text-slate-500">2FA</dt><dd>{d.two_factor_enabled ? 'on' : 'off'}</dd></div>
            </dl>
          </Card>
          {d.subpartners.length > 0 && (
            <Card title="Subpartners">
              {d.subpartners.map((s) => <Link key={s.id} to={`/admin/affiliate/partners/${s.id}`} className="mr-2 text-sm font-bold text-blue-300">{s.partner_code}</Link>)}
            </Card>
          )}
        </div>
      )}
      {tab === 'links' && (
        <Card title="Tracking links">
          <Table head={['Name', 'Code', 'Status', 'Link', '']}>
            {d.links.map((l) => (
              <tr key={l.id}>
                <Td className="font-bold">{l.name}{l.is_default && <Badge tone="blue">Default</Badge>}</Td><Td>{l.link_code}</Td><Td><Badge status={l.status}>{l.status}</Badge></Td>
                <Td className="max-w-[260px] truncate text-blue-200">{l.urls.query}</Td>
                <Td><CopyButton text={l.urls.query || ''} />{can('aff:tracking:manage') && !l.is_default && (
                  <Btn tone="ghost" small className="ml-1" onClick={async () => { try { await affAdminApi.updateLink(l.id, { status: l.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE' }); void data.reload() } catch (e) { toastError(e) } }}>
                    {l.status === 'ACTIVE' ? 'Pause' : 'Activate'}</Btn>)}</Td>
              </tr>
            ))}
          </Table>
          {d.invite_link && <div className="mt-3 flex items-center gap-2 text-xs"><span className="text-slate-400">Invite link:</span><code className="truncate">{d.invite_link}</code><CopyButton text={d.invite_link} /></div>}
        </Card>
      )}
      {tab === 'deal' && (
        <Card title="Deal history" actions={can('aff:deal:manage') && <Btn small onClick={() => setDealOpen(true)}>Change deal</Btn>}>
          <Table head={['From', 'To', 'Type', 'Revshare', 'CPA', 'Min FTD', 'Hold', 'Carryover']}>
            {d.deal_history.map((x) => (
              <tr key={x.id}><Td>{dateOnly(x.effective_from)}</Td><Td>{x.effective_to ? dateOnly(x.effective_to) : 'current'}</Td><Td>{x.deal_type}</Td>
                <Td>{pct(x.revshare_rate)}</Td><Td>{x.cpa_amount}</Td><Td>{x.min_ftd_amount}</Td><Td>{x.hold_days}d</Td>
                <Td>{x.carryover ? `on${x.carryover_cap ? ` (cap ${x.carryover_cap})` : ''}` : 'off'}</Td></tr>
            ))}
          </Table>
        </Card>
      )}
      {tab === 'ledger' && <PartnerLedger partnerId={p.id} />}
      {tab === 'withdrawals' && (
        <Card title="Recent withdrawals">
          <Table head={['#', 'Requested', 'Amount', 'Destination', 'Status']} empty={!d.withdrawals.length}>
            {d.withdrawals.map((w) => <tr key={w.id}><Td>{w.id}</Td><Td>{dateTime(w.requested_at)}</Td><Td><Money value={w.amount} /></Td><Td>{w.destination}</Td><Td><Badge status={w.status}>{w.status}</Badge></Td></tr>)}
          </Table>
        </Card>
      )}
      {tab === 'activity' && <PartnerActivity partnerId={p.id} canRisk={can('aff:risk:manage')} />}

      <DealModal open={dealOpen} partnerId={p.id} onClose={() => setDealOpen(false)} onSaved={() => { setDealOpen(false); void data.reload() }} />
      <ReasonModal action={action} onClose={() => setAction(null)} />
    </div>
  )
}

export const ReasonModal: React.FC<{ action: null | { title: string; needReason: boolean; run: (reason: string) => Promise<void> }; onClose: () => void }> = ({ action, onClose }) => {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => setReason(''), [action])
  return (
    <Modal open={action !== null} title={action?.title || ''} onClose={onClose}>
      <div className="space-y-3">
        {action?.needReason && <Field label="Reason"><textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={cx(inputCls, 'py-2')} /></Field>}
        <Btn className="w-full" busy={busy} disabled={Boolean(action?.needReason) && reason.trim().length < 3} onClick={async () => {
          setBusy(true)
          try { await action!.run(reason.trim()); showToast({ title: 'Done', type: 'success' }); onClose() } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>Confirm</Btn>
      </div>
    </Modal>
  )
}

const PartnerSettingsCard: React.FC<{ d: Awaited<ReturnType<typeof affAdminApi.partner>>; onSaved: () => void; canEdit: boolean }> = ({ d, onSaved, canEdit }) => {
  const staff = useAsync(() => affAdminApi.staff(), [])
  const [manager, setManager] = useState(d.partner.manager_id || '')
  const [subRate, setSubRate] = useState(String(Number(d.partner.subpartner_rate) * 100))
  const [busy, setBusy] = useState(false)
  return (
    <Card title="Account manager & subpartner share">
      <div className="space-y-3">
        <Field label="Manager">
          <select value={manager} onChange={(e) => setManager(e.target.value)} className={inputCls} disabled={!canEdit}>
            <option value="">—</option>
            {(staff.data?.items || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Subpartner commission %"><input inputMode="decimal" value={subRate} onChange={(e) => setSubRate(e.target.value)} className={inputCls} disabled={!canEdit} /></Field>
        {canEdit && <Btn busy={busy} onClick={async () => {
          setBusy(true)
          try { await affAdminApi.updatePartner(d.partner.id, { manager_id: manager || '', subpartner_rate: String(Number(subRate) / 100) }); onSaved() } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>Save</Btn>}
      </div>
    </Card>
  )
}

export const DealModal: React.FC<{ open: boolean; partnerId: number; onClose: () => void; onSaved: () => void }> = ({ open, partnerId, onClose, onSaved }) => {
  const plans = useAsync(() => affAdminApi.plans(), [open])
  const [form, setForm] = useState({ plan_id: '', deal_type: 'REVSHARE', revshare: '50', cpa: '0', min_ftd: '0', geo: '', hold: '14', carryover: true, cap: '', tiers: '0:25, 1000:35, 5000:45', from: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }))
  return (
    <Modal open={open} title="Change deal" onClose={onClose}>
      <div className="space-y-3">
        <Field label="Start from plan (optional)">
          <select value={form.plan_id} onChange={(e) => set('plan_id', e.target.value)} className={inputCls}>
            <option value="">Custom terms</option>
            {(plans.data?.items || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        {!form.plan_id && (
          <>
            <Field label="Type">
              <select value={form.deal_type} onChange={(e) => set('deal_type', e.target.value)} className={inputCls}>
                {['REVSHARE', 'CPA', 'HYBRID', 'TIERED'].map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            {(form.deal_type === 'REVSHARE' || form.deal_type === 'HYBRID') && <Field label="Revshare % of NGR"><input value={form.revshare} onChange={(e) => set('revshare', e.target.value)} className={inputCls} /></Field>}
            {form.deal_type === 'TIERED' && <Field label="Tiers (period NGR $ : rate %)"><input value={form.tiers} onChange={(e) => set('tiers', e.target.value)} className={inputCls} /></Field>}
            {(form.deal_type === 'CPA' || form.deal_type === 'HYBRID') && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="CPA $"><input value={form.cpa} onChange={(e) => set('cpa', e.target.value)} className={inputCls} /></Field>
                <Field label="Min FTD $"><input value={form.min_ftd} onChange={(e) => set('min_ftd', e.target.value)} className={inputCls} /></Field>
                <Field label="CPA countries" hint="e.g. IN, BD (empty = all)"><input value={form.geo} onChange={(e) => set('geo', e.target.value)} className={inputCls} /></Field>
                <Field label="Hold days"><input value={form.hold} onChange={(e) => set('hold', e.target.value)} className={inputCls} /></Field>
              </div>
            )}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.carryover} onChange={(e) => set('carryover', e.target.checked)} /> Carry negative balance over</label>
            {form.carryover && <Field label="Carryover cap $ (optional)"><input value={form.cap} onChange={(e) => set('cap', e.target.value)} className={inputCls} /></Field>}
          </>
        )}
        <Field label="Effective from" hint="Empty = today. History is kept."><input type="date" value={form.from} onChange={(e) => set('from', e.target.value)} className={inputCls} /></Field>
        <Btn className="w-full" busy={busy} onClick={async () => {
          setBusy(true)
          try {
            const body: Record<string, unknown> = form.plan_id ? { plan_id: Number(form.plan_id) } : {
              deal_type: form.deal_type, revshare_rate: String(Number(form.revshare) / 100), cpa_amount: form.cpa, min_ftd_amount: form.min_ftd,
              cpa_geo_list: form.geo.split(',').map((x) => x.trim().toUpperCase()).filter(Boolean), hold_days: Number(form.hold) || 0,
              carryover: form.carryover, carryover_cap: form.carryover && form.cap ? form.cap : undefined,
              tier_table: form.deal_type === 'TIERED' ? form.tiers.split(',').map((pair) => {
                const [min, r] = pair.split(':').map((x) => x.trim())
                return { min_ngr: min, rate: String(Number(r) / 100) }
              }) : undefined,
            }
            if (form.from) body.effective_from = form.from
            await affAdminApi.changeDeal(partnerId, body)
            onSaved()
          } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>Save deal</Btn>
      </div>
    </Modal>
  )
}

export const PartnerLedger: React.FC<{ partnerId: number }> = ({ partnerId }) => {
  const [items, setItems] = useState<LedgerEntry[]>([])
  const [cursor, setCursor] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const load = async (next?: number) => {
    setLoading(true)
    try {
      const page = await affAdminApi.ledger(partnerId, next)
      setItems((prev) => (next ? [...prev, ...page.items] : page.items))
      setCursor(page.next_cursor)
    } catch (e) { toastError(e) } finally { setLoading(false) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [partnerId])
  return (
    <Card title="Ledger">
      <Table head={['#', 'Date', 'Type', 'Bucket', 'Amount', 'After', 'Description']} empty={!items.length && !loading}>
        {items.map((e) => (
          <tr key={e.id}><Td>{e.id}</Td><Td>{dateTime(e.created_at)}</Td><Td>{e.type}</Td><Td><Badge tone="blue">{e.bucket}</Badge></Td>
            <Td><Money value={e.amount} sign className="font-bold" /></Td><Td><Money value={e.balance_after} /></Td><Td className="max-w-[240px] truncate">{e.description}</Td></tr>
        ))}
      </Table>
      {loading && <Spinner />}
      {cursor && !loading && <Btn tone="ghost" className="mt-3 w-full" onClick={() => void load(cursor)}>Load more</Btn>}
    </Card>
  )
}

const PartnerActivity: React.FC<{ partnerId: number; canRisk: boolean }> = ({ partnerId, canRisk }) => {
  const regs = useAsync(() => (canRisk ? affAdminApi.registrations(partnerId) : Promise.resolve({ items: [] })), [partnerId])
  const deps = useAsync(() => (canRisk ? affAdminApi.deposits({ partner_id: partnerId }) : Promise.resolve({ items: [] })), [partnerId])
  const [action, setAction] = useState<null | { title: string; needReason: boolean; run: (reason: string) => Promise<void> }>(null)
  if (!canRisk) return <Empty>Player-level data needs the risk permission.</Empty>
  return (
    <div className="space-y-4">
      <Card title="Registrations">
        <Table head={['#', 'Customer', 'How', 'Country', 'When', 'Status', '']} empty={!regs.data?.items.length}>
          {(regs.data?.items || []).map((r) => (
            <tr key={r.id}><Td>{r.id}</Td><Td>{r.external_customer_id}</Td><Td>{r.attribution_type}</Td><Td>{r.country || '—'}</Td><Td>{dateTime(r.registered_at)}</Td>
              <Td><Badge status={r.status === 'FRAUD' ? 'REJECTED' : 'ACTIVE'}>{r.status}</Badge></Td>
              <Td>{r.status !== 'FRAUD' && <Btn tone="ghost" small onClick={() => setAction({ title: 'Mark registration as fraud', needReason: true, run: async (reason) => { await affAdminApi.registrationFraud(r.id, reason); await regs.reload() } })}>Fraud</Btn>}</Td></tr>
          ))}
        </Table>
      </Card>
      <Card title="Deposits">
        <Table head={['#', 'Tx', 'Amount', 'USD', 'FTD', 'CPA', 'Status', '']} empty={!deps.data?.items.length}>
          {(deps.data?.items || []).map((x) => (
            <tr key={x.id}><Td>{x.id}</Td><Td>{x.external_transaction_id}</Td><Td>{x.amount} {x.currency}</Td><Td><Money value={x.amount_usd} /></Td>
              <Td>{x.is_first_deposit ? 'yes' : ''}</Td><Td>{x.qualified_for_cpa ? 'yes' : ''}</Td><Td><Badge status={x.is_fraud ? 'REJECTED' : x.status}>{x.is_fraud ? 'FRAUD' : x.status}</Badge></Td>
              <Td>{!x.is_fraud && <Btn tone="ghost" small onClick={() => setAction({ title: 'Mark deposit as fraud (reverses CPA)', needReason: true, run: async (reason) => { await affAdminApi.depositFraud(x.id, reason); await deps.reload() } })}>Fraud</Btn>}</Td></tr>
          ))}
        </Table>
      </Card>
      <ReasonModal action={action} onClose={() => setAction(null)} />
    </div>
  )
}
