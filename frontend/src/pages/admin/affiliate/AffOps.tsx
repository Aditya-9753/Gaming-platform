import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, Download, Globe, RefreshCw, Upload, Users, Wallet } from 'lucide-react'
import {
  Badge, Btn, Card, ErrorBox, Field, Modal, Money, Spinner, Table, Tabs, Td, cx, dateTime, inputCls, toastError, useAsync,
} from '../../../components/affiliate/ui'
import { showToast } from '../../../components/common/Toast'
import { usePermission } from '../../../hooks/usePermission'
import { affAdminApi, saveBlob } from '../../../services/affiliateAdmin.api'
import type { IngestEvent } from '../../../types/affiliate.types'
import { ReasonModal } from './AffPartners'

export const AffOverview: React.FC = () => {
  const data = useAsync(() => affAdminApi.overview(), [])
  if (data.loading && !data.data) return <Spinner />
  if (data.error) return <ErrorBox message={data.error} onRetry={data.reload} />
  const d = data.data!
  const month = d.this_month.reduce((a, r) => ({ clicks: a.clicks + r.clicks, regs: a.regs + r.registrations, ftd: a.ftd + r.first_deposits,
    dep: a.dep + Number(r.deposit_amount), income: a.income + Number(r.income) }), { clicks: 0, regs: 0, ftd: 0, dep: 0, income: 0 })
  const tile = (icon: React.ReactNode, label: string, value: React.ReactNode, to?: string, alert?: boolean) => {
    const body = (
      <div className={cx('rounded-2xl border p-4', alert ? 'border-rose-500/40 bg-rose-500/10' : 'border-dark-border bg-dark-card')}>
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase text-slate-400">{icon}{label}</div>
        <div className="mt-1 text-xl font-black">{value}</div>
      </div>
    )
    return to ? <Link to={to}>{body}</Link> : body
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Affiliate overview</h1>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tile(<Users className="h-4 w-4" />, 'Active partners', d.partners.ACTIVE || 0, '/admin/affiliate/partners?status=ACTIVE')}
        {tile(<Users className="h-4 w-4" />, 'Waiting approval', d.partners.PENDING || 0, '/admin/affiliate/partners?status=PENDING', (d.partners.PENDING || 0) > 0)}
        {tile(<Wallet className="h-4 w-4" />, 'Open withdrawals', <span>{d.open_withdrawals.count} · <Money value={d.open_withdrawals.amount} /></span>, '/admin/affiliate/withdrawals')}
        {tile(<AlertTriangle className="h-4 w-4" />, 'Open risk events', d.open_risk_events, '/admin/affiliate/risk', d.open_risk_events > 0)}
        {tile(<Activity className="h-4 w-4" />, 'Failed ingest events', d.failed_ingest, '/admin/affiliate/ingest', d.failed_ingest > 0)}
        {tile(<Wallet className="h-4 w-4" />, 'Adjustments to approve', d.pending_adjustments, '/admin/affiliate/adjustments', d.pending_adjustments > 0)}
        {tile(<Wallet className="h-4 w-4" />, 'Owed (available)', <Money value={d.balances.available} />)}
        {tile(<Wallet className="h-4 w-4" />, 'Pending commission', <Money value={d.balances.pending} />)}
      </div>
      <Card title={`This month · period ${d.current_period.start_date} – ${d.current_period.end_date}`}>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
          {[['Clicks', month.clicks], ['Registrations', month.regs], ['First deposits', month.ftd]].map(([k, v]) => <div key={String(k)}><div className="text-[11px] text-slate-500">{k}</div><div className="font-black">{v}</div></div>)}
          <div><div className="text-[11px] text-slate-500">Deposits</div><Money value={month.dep} className="font-black" /></div>
          <div><div className="text-[11px] text-slate-500">Partner income</div><Money value={month.income} className="font-black" /></div>
        </div>
      </Card>
    </div>
  )
}

// ============================================================ tracking domains

export const AffDomains: React.FC = () => {
  const data = useAsync(() => affAdminApi.domains(), [])
  const { isSuperAdmin } = usePermission()
  const [form, setForm] = useState({ domain: '', is_primary: false })
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Tracking domains</h1>
      <p className="text-xs text-slate-400">Partner links are built on the primary active domain: <code className="text-blue-300">{data.data?.link_base}</code>.
        If a domain gets blocked in a GEO, add a mirror and make it primary — every partner link switches without new codes.</p>
      {isSuperAdmin() && (
        <Card title="Add domain">
          <div className="flex flex-wrap gap-2">
            <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="go.example.com" className={cx(inputCls, 'flex-1')} />
            <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} />Primary</label>
            <Btn busy={busy} disabled={!form.domain} onClick={async () => {
              setBusy(true)
              try { await affAdminApi.addDomain({ ...form, status: 'ACTIVE' }); setForm({ domain: '', is_primary: false }); void data.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
            }}>Add</Btn>
          </div>
        </Card>
      )}
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['Domain', 'Primary', 'Status', 'TLS', 'Checked', '']} empty={!data.data?.items.length} emptyText="No domain yet — links use the main site address.">
            {(data.data?.items || []).map((d) => (
              <tr key={d.id}>
                <Td className="font-bold"><Globe className="mr-1 inline h-3.5 w-3.5" />{d.domain}</Td><Td>{d.is_primary ? <Badge tone="blue">primary</Badge> : 'mirror'}</Td>
                <Td><Badge status={d.status}>{d.status}</Badge></Td><Td>{d.ssl_ok === null ? '—' : d.ssl_ok ? '✓' : <span className="text-rose-300" title={d.last_check_error || ''}>✗</span>}</Td>
                <Td>{dateTime(d.last_checked_at)}</Td>
                <Td className="space-x-1">{isSuperAdmin() && (
                  <>
                    <Btn tone="ghost" small onClick={async () => { try { await affAdminApi.checkDomain(d.id); void data.reload() } catch (e) { toastError(e) } }}>Check</Btn>
                    {!d.is_primary && <Btn tone="ghost" small onClick={async () => { try { await affAdminApi.editDomain(d.id, { domain: d.domain, is_primary: true, status: 'ACTIVE' }); void data.reload() } catch (e) { toastError(e) } }}>Make primary</Btn>}
                    <Btn tone="ghost" small onClick={async () => { try { await affAdminApi.editDomain(d.id, { domain: d.domain, is_primary: false, status: d.status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE' }); void data.reload() } catch (e) { toastError(e) } }}>
                      {d.status === 'ACTIVE' ? 'Mark blocked' : 'Activate'}</Btn>
                  </>
                )}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}

// ============================================================ statistics

export const AffStatistics: React.FC = () => {
  const [groupBy, setGroupBy] = useState('partner')
  const [period, setPeriod] = useState('30d')
  const data = useAsync(() => affAdminApi.statistics({ group_by: groupBy, period }), [groupBy, period])
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-black">Affiliate statistics</h1>
        <div className="flex flex-wrap gap-2">
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className={cx(inputCls, 'w-auto')}>
            {['partner', 'day', 'country', 'source', 'link'].map((g) => <option key={g} value={g}>By {g}</option>)}
          </select>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} className={cx(inputCls, 'w-auto')}>
            {[['today', 'Today'], ['7d', '7 days'], ['30d', '30 days'], ['this_month', 'This month'], ['last_month', 'Last month'], ['all', 'All time']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <Btn tone="ghost" onClick={async () => { try { saveBlob(await affAdminApi.statisticsCsv({ group_by: groupBy, period }), `affiliate-${groupBy}-${period}.csv`) } catch (e) { toastError(e) } }}><Download className="h-4 w-4" />CSV</Btn>
          <Btn tone="ghost" busy={busy} onClick={async () => {
            setBusy(true)
            try { const r = await affAdminApi.rebuildAnalytics(3); showToast({ title: `Rebuilt ${r.rows} rows`, type: 'success' }); void data.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
          }}><RefreshCw className="h-4 w-4" />Rebuild</Btn>
        </div>
      </div>
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['', 'Clicks', 'Reg.', 'Clicks/reg', 'FTD', 'Deposits', 'NGR', 'Partner income', 'EPC']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((r) => (
              <tr key={String(r.key)}>
                <Td className="font-bold">{groupBy === 'partner' ? <Link to={`/admin/affiliate/partners/${r.key}`} className="text-blue-300">{r.label}</Link> : r.label}</Td>
                <Td>{r.clicks}</Td><Td>{r.registrations}</Td><Td>{r.ratio_registrations ?? '—'}</Td><Td>{r.first_deposits}</Td>
                <Td><Money value={r.deposit_amount} /></Td><Td><Money value={r.ngr} /></Td><Td><Money value={r.income} className="font-bold" /></Td><Td>{r.cost_transition ?? '—'}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}

// ============================================================ risk

export const AffRisk: React.FC = () => {
  const [status, setStatus] = useState('OPEN')
  const data = useAsync(() => affAdminApi.riskEvents({ status: status || undefined }), [status])
  const [ipAction, setIpAction] = useState<null | { title: string; needReason: boolean; run: (r: string) => Promise<void> }>(null)
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Risk</h1>
      <Tabs value={status} onChange={setStatus} tabs={[{ id: 'OPEN', label: 'Open' }, { id: 'REVIEWED', label: 'Reviewed' }, { id: 'CONFIRMED', label: 'Confirmed' }, { id: 'DISMISSED', label: 'Dismissed' }, { id: '', label: 'All' }]} />
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['When', 'Severity', 'Type', 'Partner', 'Reason', 'Status', '']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((r) => (
              <tr key={r.id}>
                <Td>{dateTime(r.created_at)}</Td><Td><Badge status={r.severity}>{r.severity}</Badge></Td><Td>{r.event_type}</Td>
                <Td>{r.partner_id ? <Link to={`/admin/affiliate/partners/${r.partner_id}`} className="text-blue-300">#{r.partner_id}</Link> : '—'}</Td>
                <Td className="max-w-[320px] whitespace-normal">{r.reason}</Td><Td><Badge status={r.status}>{r.status}</Badge></Td>
                <Td className="space-x-1">
                  {r.status === 'OPEN' && ['CONFIRMED', 'DISMISSED', 'REVIEWED'].map((s) => (
                    <Btn key={s} tone={s === 'CONFIRMED' ? 'danger' : 'ghost'} small onClick={async () => { try { await affAdminApi.reviewRisk(r.id, s); void data.reload() } catch (e) { toastError(e) } }}>{s.toLowerCase()}</Btn>
                  ))}
                  {r.event_type === 'CLICK_FLOOD' && r.partner_id && (
                    <Btn tone="ghost" small onClick={() => setIpAction({ title: 'Mark the partner\'s recent bot clicks as fraud', needReason: true, run: async (reason) => {
                      const clicks = await affAdminApi.clicks(r.partner_id!)
                      const ips = [...new Set(clicks.items.filter((c) => c.is_bot && c.ip_hash).map((c) => c.ip_hash!))]
                      let marked = 0
                      for (const ip of ips) marked += (await affAdminApi.ipFraud({ partner_id: r.partner_id, ip_hash: ip, hours: 48, reason })).marked
                      showToast({ title: `${marked} clicks marked as fraud`, type: 'success' })
                    } })}>Clicks → fraud</Btn>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <ReasonModal action={ipAction} onClose={() => setIpAction(null)} />
    </div>
  )
}

// ============================================================ ingest monitor

export const AffIngest: React.FC = () => {
  const [status, setStatus] = useState('FAILED')
  const data = useAsync(() => affAdminApi.ingestEvents({ status: status || undefined }), [status])
  const [view, setView] = useState<IngestEvent | null>(null)
  const [csvOpen, setCsvOpen] = useState(false)
  const [csv, setCsv] = useState({ event_type: 'REVENUE', csv: '' })
  const [busy, setBusy] = useState(false)
  const counts = data.data?.counts || {}
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-black">Ingest monitor</h1>
        <Btn tone="ghost" onClick={() => setCsvOpen(true)}><Upload className="h-4 w-4" />CSV upload</Btn>
      </div>
      <p className="text-xs text-slate-400">Operator events (S2S, internal Rudra247 bridge, CSV) are stored raw first, then processed. Failed ones retry automatically up to 8 times.</p>
      <Tabs value={status} onChange={setStatus} tabs={['FAILED', 'RECEIVED', 'PROCESSED', 'IGNORED', ''].map((s) => ({ id: s, label: `${s || 'All'}${s && counts[s] !== undefined ? ` (${counts[s]})` : ''}` }))} />
      <Card>
        {data.loading && !data.data ? <Spinner /> : (
          <Table head={['#', 'Type', 'Key', 'Source', 'Status', 'Attempts', 'Received', 'Error', '']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((e) => (
              <tr key={e.id}>
                <Td>{e.id}</Td><Td>{e.event_type}</Td><Td className="max-w-[160px] truncate">{e.idempotency_key}</Td><Td>{e.source}</Td>
                <Td><Badge status={e.status}>{e.status}</Badge></Td><Td>{e.attempts}</Td><Td>{dateTime(e.received_at)}</Td>
                <Td className="max-w-[260px] truncate text-rose-300">{e.error}</Td>
                <Td className="space-x-1">
                  <Btn tone="ghost" small onClick={async () => setView(await affAdminApi.ingestEvent(e.id))}>Payload</Btn>
                  {(e.status === 'FAILED' || e.status === 'IGNORED') && <Btn small onClick={async () => { try { await affAdminApi.retryIngest(e.id); void data.reload() } catch (err) { toastError(err) } }}>Retry</Btn>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Modal open={view !== null} title={`Event #${view?.id}`} onClose={() => setView(null)} wide>
        <pre className="max-h-[60dvh] overflow-auto rounded-xl bg-dark-bg p-3 text-[11px] text-slate-300">{JSON.stringify(view?.payload, null, 2)}</pre>
      </Modal>
      <Modal open={csvOpen} title="Upload operator CSV" onClose={() => setCsvOpen(false)} wide>
        <div className="space-y-3">
          <Field label="Event type">
            <select value={csv.event_type} onChange={(e) => setCsv({ ...csv, event_type: e.target.value })} className={inputCls}>
              {['REGISTRATION', 'DEPOSIT', 'REVENUE', 'REVERSAL'].map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <p className="text-[11px] text-slate-500">
            REGISTRATION: external_customer_id, click_id, promo_code, country, registered_at · DEPOSIT: external_customer_id, external_transaction_id, amount, currency, status, completed_at ·
            REVENUE: external_customer_id, date, bets, wins, bonuses, fees, chargebacks, currency · REVERSAL: external_reversal_id, external_transaction_id, amount, reason
          </p>
          <input type="file" accept=".csv,text/csv" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setCsv({ ...csv, csv: await f.text() }) }} className="text-xs" />
          <textarea value={csv.csv} onChange={(e) => setCsv({ ...csv, csv: e.target.value })} rows={6} className={cx(inputCls, 'py-2 font-mono text-[11px]')} placeholder="header row, then data" />
          <Btn className="w-full" busy={busy} disabled={csv.csv.length < 10} onClick={async () => {
            setBusy(true)
            try { const r = await affAdminApi.ingestCsv(csv.event_type, csv.csv); showToast({ title: 'Imported', message: JSON.stringify(r), type: 'success' }); setCsvOpen(false); void data.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Import</Btn>
        </div>
      </Modal>
    </div>
  )
}

// ============================================================ audit

export const AffAudit: React.FC = () => {
  const [type, setType] = useState('')
  const data = useAsync(() => affAdminApi.auditLogs({ target_type: type || undefined, limit: 100 }), [type])
  const [open, setOpen] = useState<Record<string, unknown> | null>(null)
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Affiliate audit log</h1>
      <select value={type} onChange={(e) => setType(e.target.value)} className={cx(inputCls, 'w-auto')}>
        <option value="">All</option>
        {['aff_partner', 'aff_withdrawal', 'aff_manual_adjustment', 'aff_settlement_period', 'aff_tracking_domain', 'aff_tracking_link', 'aff_commission', 'aff_settings', 'user'].map((t) => <option key={t}>{t}</option>)}
      </select>
      <Card>
        {data.loading && !data.data ? <Spinner /> : data.error ? <ErrorBox message={data.error} /> : (
          <Table head={['When', 'Who', 'Action', 'Target', '']} empty={!data.data?.items.length}>
            {(data.data?.items || []).map((a) => (
              <tr key={a.id}><Td>{dateTime(a.created_at)}</Td><Td>{a.actor}</Td><Td className="font-bold">{a.action}</Td><Td>{a.target_type} {a.target_id}</Td>
                <Td>{a.details && <Btn tone="ghost" small onClick={() => setOpen(a.details)}>Details</Btn>}</Td></tr>
            ))}
          </Table>
        )}
      </Card>
      <Modal open={open !== null} title="Details (old → new)" onClose={() => setOpen(null)} wide>
        <pre className="max-h-[60dvh] overflow-auto rounded-xl bg-dark-bg p-3 text-[11px]">{JSON.stringify(open, null, 2)}</pre>
      </Modal>
    </div>
  )
}

