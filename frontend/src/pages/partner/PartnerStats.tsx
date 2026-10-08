import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Download, FileDown } from 'lucide-react'
import { Badge, Btn, Card, CopyButton, Empty, ErrorBox, Money, Spinner, Table, Tabs, Td, cx, dateOnly, inputCls, pct, toastError, useAsync } from '../../components/affiliate/ui'
import { saveBlob } from '../../services/affiliateAdmin.api'
import { partnerApi, type StatsQuery } from '../../services/affiliate.api'
import type { ExportJob } from '../../types/affiliate.types'
import { useT } from './i18n'
import { usePartnerStore } from './partner.store'
import { PeriodPicker } from './PartnerDashboard'

const GROUPS = [['day', 'Day'], ['source', 'Source'], ['link', 'Link'], ['campaign', 'Campaign'], ['country', 'Country'], ['sub1', 'Sub1']]

export const PartnerStatistics: React.FC = () => {
  const t = useT()
  const me = usePartnerStore((s) => s.me)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'subpartners' ? 'subpartners' : 'common'
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('statistics')}</h1>
      {me?.subpartners_enabled && (
        <Tabs value={tab} onChange={(id) => setParams(id === 'common' ? {} : { tab: id })}
          tabs={[{ id: 'common', label: t('common') }, { id: 'subpartners', label: t('subpartners') }]} />
      )}
      {tab === 'common' ? <CommonStats /> : <SubpartnerStats />}
    </div>
  )
}

const CommonStats: React.FC = () => {
  const [groupBy, setGroupBy] = useState('day')
  const [query, setQuery] = useState<StatsQuery>({ period: '30d' })
  const [applied, setApplied] = useState<{ groupBy: string; query: StatsQuery }>({ groupBy: 'day', query: { period: '30d' } })
  const data = useAsync(() => partnerApi.statistics(applied.groupBy, applied.query), [applied])
  const [jobs, setJobs] = useState<ExportJob[]>([])
  const refreshJobs = () => partnerApi.exports().then((r) => setJobs(r.items)).catch(() => undefined)
  useEffect(() => { void refreshJobs() }, [])
  useEffect(() => {
    if (!jobs.some((j) => j.status === 'PENDING')) return
    const timer = setTimeout(refreshJobs, 2000)
    return () => clearTimeout(timer)
  }, [jobs])

  const rows = data.data?.items || []
  const totals = rows.reduce((acc, r) => ({
    clicks: acc.clicks + r.clicks, registrations: acc.registrations + r.registrations, first_deposits: acc.first_deposits + r.first_deposits,
    deposit_amount: acc.deposit_amount + Number(r.deposit_amount), income: acc.income + Number(r.income),
  }), { clicks: 0, registrations: 0, first_deposits: 0, deposit_amount: 0, income: 0 })

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className={cx(inputCls, 'w-auto')} aria-label="Group by">
            {GROUPS.map(([id, label]) => <option key={id} value={id}>By {label.toLowerCase()}</option>)}
          </select>
          <PeriodPicker value={query} onChange={setQuery} />
          <Btn onClick={() => setApplied({ groupBy, query })}>Apply</Btn>
          <Btn tone="ghost" onClick={async () => {
            try {
              await partnerApi.exportStats({ kind: 'common', group_by: applied.groupBy, period: applied.query.period, date_from: applied.query.date_from, date_to: applied.query.date_to })
              await refreshJobs()
            } catch (e) { toastError(e) }
          }}><FileDown className="h-4 w-4" />Export CSV</Btn>
        </div>
      </Card>
      <Card>
        {data.loading && !data.data ? <Spinner /> : data.error ? <ErrorBox message={data.error} onRetry={data.reload} /> : (
          <Table head={['', 'Clicks', 'Registrations', 'Ratio', 'FTD', 'Deposits $', 'Income $', 'EPC']} empty={!rows.length}>
            {rows.map((r) => (
              <tr key={String(r.key)}>
                <Td className="font-bold">{applied.groupBy === 'day' ? dateOnly(String(r.label)) : r.label}</Td>
                <Td>{r.clicks}</Td><Td>{r.registrations}</Td><Td>{r.ratio_registrations ?? '—'}</Td><Td>{r.first_deposits}</Td>
                <Td><Money value={r.deposit_amount} /></Td><Td><Money value={r.income} className="font-bold" /></Td><Td>{r.cost_transition ?? '—'}</Td>
              </tr>
            ))}
            {rows.length > 0 && (
              <tr className="bg-dark-elevated/50 font-black">
                <Td>Total</Td><Td>{totals.clicks}</Td><Td>{totals.registrations}</Td>
                <Td>{totals.registrations ? (totals.clicks / totals.registrations).toFixed(2) : '—'}</Td><Td>{totals.first_deposits}</Td>
                <Td><Money value={totals.deposit_amount} /></Td><Td><Money value={totals.income} /></Td>
                <Td>{totals.clicks ? (totals.income / totals.clicks).toFixed(2) : '—'}</Td>
              </tr>
            )}
          </Table>
        )}
      </Card>
      {jobs.length > 0 && (
        <Card title="Exports">
          <div className="space-y-2">
            {jobs.slice(0, 5).map((j) => (
              <div key={j.id} className="flex flex-wrap items-center gap-2 text-xs">
                <Badge status={j.status === 'DONE' ? 'COMPLETED' : j.status}>{j.status}</Badge>
                <span className="text-slate-300">{String(j.params.group_by || j.type)} · {String(j.params.period)}</span>
                <span className="text-slate-500">{j.row_count} rows</span>
                {j.status === 'DONE' && (
                  <Btn tone="ghost" small className="ml-auto" onClick={async () => saveBlob(await partnerApi.downloadExport(j.id), `statistics-${j.id}.csv`)}>
                    <Download className="h-3.5 w-3.5" />Download
                  </Btn>
                )}
                {j.error && <span className="text-rose-300">{j.error}</span>}
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}

const SubpartnerStats: React.FC = () => {
  const [query, setQuery] = useState<StatsQuery>({ period: 'all' })
  const data = useAsync(() => partnerApi.subpartnerStats(query), [query])
  return (
    <Card actions={<PeriodPicker value={query} onChange={setQuery} />} title="Your subpartners">
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={['Partner', 'Status', 'Clicks', 'Registrations', 'FTD', 'Their income', 'Your commission']} empty={!data.data?.items.length}
          emptyText="No subpartners yet — share your invite link from the Subpartners page.">
          {(data.data?.items || []).map((r) => (
            <tr key={r.partner_code}>
              <Td className="font-bold">{r.partner_code}<div className="text-[10px] font-normal text-slate-500">{r.email_masked}</div></Td>
              <Td><Badge status={r.status}>{r.status}</Badge></Td><Td>{r.clicks}</Td><Td>{r.registrations}</Td><Td>{r.first_deposits}</Td>
              <Td><Money value={r.income} /></Td><Td><Money value={r.your_commission} className="font-bold text-emerald-300" /></Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  )
}

export const PartnerSubpartners: React.FC = () => {
  const t = useT()
  const data = useAsync(() => partnerApi.subpartners(), [])
  if (data.loading && !data.data) return <Spinner />
  if (data.error) return <ErrorBox message={data.error} onRetry={data.reload} />
  const d = data.data!
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('subpartners')}</h1>
      {d.invite_link ? (
        <Card title="Invite partners and earn from their commission">
          <p className="mb-3 text-sm text-slate-300">You earn <b className="text-emerald-300">{pct(d.rate)}</b> of every direct subpartner's positive commission each period. A subpartner's negative period never costs you.</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg bg-dark-elevated px-2 py-2 text-xs text-blue-200">{d.invite_link}</code>
            <CopyButton text={d.invite_link} label="Copy" />
          </div>
        </Card>
      ) : <Card><p className="text-sm text-slate-400">Subpartner invites are not available for this account.</p></Card>}
      <Card title="Subpartners">
        {d.items.length === 0 ? <Empty>No subpartners yet.</Empty> : (
          <Table head={['Partner', 'Status', 'Joined', 'Registrations', 'FTD', 'Your commission']}>
            {d.items.map((r) => (
              <tr key={r.partner_code}>
                <Td className="font-bold">{r.partner_code}<div className="text-[10px] font-normal text-slate-500">{r.email_masked}</div></Td>
                <Td><Badge status={r.status}>{r.status}</Badge></Td><Td>{dateOnly(r.joined_at)}</Td><Td>{r.registrations}</Td><Td>{r.first_deposits}</Td>
                <Td><Money value={r.your_commission} className="font-bold" /></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
