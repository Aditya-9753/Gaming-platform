import React, { useEffect, useState } from 'react'
import { Maximize2, SlidersHorizontal } from 'lucide-react'
import { DualAxisChart } from '../../components/affiliate/DualAxisChart'
import { Btn, Card, ErrorBox, Field, Modal, Money, Spinner, cx, errorText, inputCls } from '../../components/affiliate/ui'
import { partnerApi, type StatsQuery } from '../../services/affiliate.api'
import type { FilterOptions, Kpis, SeriesPoint } from '../../types/affiliate.types'
import { useT, type TKey } from './i18n'

export const PERIODS: Array<[string, TKey]> = [
  ['all', 'forAllTime'], ['today', 'today'], ['yesterday', 'yesterday'], ['7d', 'last7'], ['30d', 'last30'],
  ['this_month', 'thisMonth'], ['last_month', 'lastMonth'], ['custom', 'custom'],
]

export const PeriodPicker: React.FC<{ value: StatsQuery; onChange: (q: StatsQuery) => void }> = ({ value, onChange }) => {
  const t = useT()
  return (
    <div className="flex flex-wrap items-end gap-2">
      <select value={value.period} onChange={(e) => onChange({ ...value, period: e.target.value })} className={cx(inputCls, 'w-auto min-w-[160px]')} aria-label="Period">
        {PERIODS.map(([id, key]) => <option key={id} value={id}>{t(key)}</option>)}
      </select>
      {value.period === 'custom' && (
        <>
          <input type="date" value={value.date_from || ''} onChange={(e) => onChange({ ...value, date_from: e.target.value })} className={cx(inputCls, 'w-auto')} aria-label="From" />
          <input type="date" value={value.date_to || ''} onChange={(e) => onChange({ ...value, date_to: e.target.value })} className={cx(inputCls, 'w-auto')} aria-label="To" />
        </>
      )}
    </div>
  )
}

const Metric: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5 last:border-0">
    <span className="text-xs text-blue-100/80">{label}</span>
    <span className="text-sm font-black tabular-nums text-white">{value ?? '—'}</span>
  </div>
)

const dash = (v: string | null | undefined) => (v === null || v === undefined ? '—' : v)

export const PartnerDashboard: React.FC = () => {
  const t = useT()
  const [kpiQuery, setKpiQuery] = useState<StatsQuery>({ period: 'all' })
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [kpiError, setKpiError] = useState<string | null>(null)
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [draft, setDraft] = useState<StatsQuery>({ period: '30d', source_ids: [], link_ids: [], countries: [] })
  const [chartQuery, setChartQuery] = useState<StatsQuery>(draft)
  const [series, setSeries] = useState<SeriesPoint[] | null>(null)
  const [full, setFull] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)

  useEffect(() => {
    if (kpiQuery.period === 'custom' && (!kpiQuery.date_from || !kpiQuery.date_to)) return
    setKpis(null)
    partnerApi.summary(kpiQuery).then(setKpis).catch((e) => setKpiError(errorText(e)))
  }, [kpiQuery])
  useEffect(() => { partnerApi.filters().then(setOptions).catch(() => setOptions({ sources: [], links: [], countries: [] })) }, [])
  useEffect(() => {
    if (chartQuery.period === 'custom' && (!chartQuery.date_from || !chartQuery.date_to)) return
    setSeries(null)
    partnerApi.timeseries(chartQuery).then((r) => setSeries(r.series)).catch(() => setSeries([]))
  }, [chartQuery])

  const toggle = (key: 'source_ids' | 'link_ids' | 'countries', id: number | string) =>
    setDraft((d) => {
      const list = (d[key] as Array<number | string>) || []
      return { ...d, [key]: list.includes(id) ? list.filter((x) => x !== id) : [...list, id] }
    })

  const chartSeries = [
    { key: 'referrals', label: t('referrals'), color: '#60a5fa', axis: 'count' as const },
    { key: 'registrations', label: t('registrations'), color: '#a78bfa', axis: 'count' as const },
    { key: 'first_deposits', label: t('firstDeposits'), color: '#34d399', axis: 'count' as const },
    { key: 'income', label: t('income'), color: '#f472b6', axis: 'usd' as const },
    { key: 'deposit_amount', label: t('amountDeposits'), color: '#fbbf24', axis: 'usd' as const },
  ]
  const points = (series || []).map((p) => ({ ...p, income: Number(p.income), deposit_amount: Number(p.deposit_amount) }))
  const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: '2-digit', month: 'short' })
  const chart = <DualAxisChart points={points} xKey="date" series={chartSeries} formatX={shortDate} height={full ? 360 : 240} />

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-[#1d3b8f] to-[#14245a] shadow-xl">
        <div className="flex items-center justify-between gap-2 p-4 pb-2">
          <h1 className="text-base font-black">{t('dashboard')}</h1>
          <PeriodPicker value={kpiQuery} onChange={setKpiQuery} />
        </div>
        {kpiError && <div className="px-4 pb-4"><ErrorBox message={kpiError} /></div>}
        {!kpis && !kpiError && <Spinner />}
        {kpis && (
          <>
            <div className="px-4 pb-2">
              <Metric label={t('transition')} value={kpis.transitions.toLocaleString()} />
              <Metric label={t('registration')} value={kpis.registrations.toLocaleString()} />
              <Metric label={t('firstDeposits')} value={kpis.first_deposits.toLocaleString()} />
              <Metric label={t('numberDeposits')} value={kpis.deposit_count.toLocaleString()} />
              <Metric label={t('ratioRegistrations')} value={dash(kpis.ratio_registrations)} />
              <Metric label={t('ratioDeposits')} value={dash(kpis.ratio_deposits)} />
              <Metric label={t('amountDeposit')} value={<Money value={kpis.amount_deposit} />} />
              <Metric label={t('costTransition')} value={kpis.cost_transition === null ? '—' : <Money value={kpis.cost_transition} />} />
              <Metric label={t('avgPlayerIncome')} value={kpis.avg_player_income === null ? '—' : <Money value={kpis.avg_player_income} />} />
            </div>
            <div className="flex items-center justify-between bg-purple-600 px-4 py-3">
              <span className="text-sm font-black">{t('income')}</span>
              <Money value={kpis.income} className={cx('text-lg font-black', Number(kpis.income) < 0 ? 'text-rose-100' : 'text-white')} />
            </div>
          </>
        )}
      </section>

      <Card title={t('statistics')} actions={
        <>
          <Btn tone="ghost" small onClick={() => setFiltersOpen(true)}><SlidersHorizontal className="h-4 w-4" />Filters</Btn>
          <Btn tone="ghost" small onClick={() => setFull(true)} aria-label="Full screen"><Maximize2 className="h-4 w-4" /></Btn>
        </>
      }>
        <div className="mb-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
          <span>{PERIODS.find(([id]) => id === chartQuery.period)?.[1] ? t(PERIODS.find(([id]) => id === chartQuery.period)![1]) : ''}</span>
          {chartQuery.source_ids?.length ? <span>· {chartQuery.source_ids.length} source(s)</span> : <span>· {t('allSources')}</span>}
          {chartQuery.link_ids?.length ? <span>· {chartQuery.link_ids.length} link(s)</span> : <span>· {t('allLinks')}</span>}
          {chartQuery.countries?.length ? <span>· {chartQuery.countries.join(', ')}</span> : <span>· {t('allCountries')}</span>}
        </div>
        {series === null ? <Spinner /> : series.length === 0 ? <p className="py-8 text-center text-sm text-slate-500">{t('noData')}</p> : chart}
      </Card>

      <Modal open={filtersOpen} title="Filters" onClose={() => setFiltersOpen(false)}>
        <div className="space-y-4">
          <Field label="Period"><PeriodPicker value={draft} onChange={setDraft} /></Field>
          {options && (
            <>
              <Chips label={t('sources')} items={options.sources.map((s) => ({ id: s.id, label: s.name }))} selected={draft.source_ids || []} onToggle={(id) => toggle('source_ids', id)} />
              <Chips label="Links" items={options.links.map((l) => ({ id: l.id, label: `${l.name} · ${l.code}` }))} selected={draft.link_ids || []} onToggle={(id) => toggle('link_ids', id)} />
              <Chips label="Countries" items={options.countries.map((c) => ({ id: c, label: c }))} selected={draft.countries || []} onToggle={(id) => toggle('countries', id)} />
            </>
          )}
          <Btn className="w-full" onClick={() => { setChartQuery(draft); setFiltersOpen(false) }}>{t('apply')}</Btn>
        </div>
      </Modal>

      {full && (
        <div className="fixed inset-0 z-[90] flex flex-col bg-dark-bg p-3" role="dialog" aria-label="Chart full screen">
          <div className="mb-2 flex justify-end"><Btn tone="ghost" small onClick={() => setFull(false)}>Close</Btn></div>
          <div className="flex flex-1 items-center overflow-auto landscape:items-stretch">
            <div className="w-full min-w-[640px]">{chart}</div>
          </div>
        </div>
      )}
    </div>
  )
}

const Chips: React.FC<{ label: string; items: Array<{ id: number | string; label: string }>; selected: Array<number | string>; onToggle: (id: number | string) => void }> = ({ label, items, selected, onToggle }) => (
  <Field label={label}>
    {items.length === 0 ? <p className="text-xs text-slate-500">—</p> : (
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button key={item.id} type="button" onClick={() => onToggle(item.id)} aria-pressed={selected.includes(item.id)}
            className={cx('min-h-[36px] rounded-full border px-3 text-xs font-bold', selected.includes(item.id) ? 'border-brand-blue bg-brand-blue/20 text-white' : 'border-dark-border text-slate-400')}>
            {item.label}
          </button>
        ))}
      </div>
    )}
  </Field>
)
