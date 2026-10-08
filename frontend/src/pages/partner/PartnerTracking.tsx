import React, { useMemo, useState } from 'react'
import { Download, ExternalLink, Link2, Plus, QrCode as QrIcon } from 'lucide-react'
import {
  Badge, Btn, Card, CopyButton, Empty, ErrorBox, Field, Modal, Spinner, Tabs, cx, inputCls, toastError, useAsync,
} from '../../components/affiliate/ui'
import { showToast } from '../../components/common/Toast'
import { partnerApi } from '../../services/affiliate.api'
import type { Campaign, Source, TrackingLink } from '../../types/affiliate.types'
import { useT } from './i18n'

const SOURCE_TYPES = ['WEBSITE', 'SOCIAL', 'TELEGRAM', 'YOUTUBE', 'PAID_ADS', 'OTHER']

const withSubs = (url: string, subs: Record<string, string>) => {
  const extra = Object.entries(subs).filter(([, v]) => v.trim()).map(([k, v]) => `${k}=${encodeURIComponent(v.trim())}`).join('&')
  if (!extra) return url
  return url + (url.includes('?') ? '&' : '?') + extra
}

export const PartnerSources: React.FC = () => {
  const t = useT()
  const [tab, setTab] = useState('links')
  const sources = useAsync(() => partnerApi.sources(), [])
  const campaigns = useAsync(() => partnerApi.campaigns(), [])
  const links = useAsync(() => partnerApi.links(), [])
  const promos = useAsync(() => partnerApi.promos(), [])
  const reloadAll = () => { void sources.reload(); void campaigns.reload(); void links.reload(); void promos.reload() }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('sources')}</h1>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'links', label: 'Tracking links' }, { id: 'sources', label: t('sources') },
        { id: 'campaigns', label: 'Campaigns' }, { id: 'promo', label: 'Promo codes' },
      ]} />
      {tab === 'links' && <LinksPanel links={links} sources={sources.data?.items || []} campaigns={campaigns.data?.items || []} onChange={reloadAll} />}
      {tab === 'sources' && <SourcesPanel state={sources} onChange={reloadAll} />}
      {tab === 'campaigns' && <CampaignsPanel state={campaigns} sources={sources.data?.items || []} onChange={reloadAll} />}
      {tab === 'promo' && <PromoPanel state={promos} links={links.data?.items || []} onChange={reloadAll} />}
    </div>
  )
}

type Loaded<T> = { data: T | null; loading: boolean; error: string | null; reload: () => Promise<void> }

const LinksPanel: React.FC<{ links: Loaded<{ items: TrackingLink[]; base_url: string; mirrors: string[] }>; sources: Source[]; campaigns: Campaign[]; onChange: () => void }> = ({ links, sources, campaigns, onChange }) => {
  const [open, setOpen] = useState(false)
  const [builder, setBuilder] = useState<TrackingLink | null>(null)
  const [form, setForm] = useState({ name: '', source_id: '', campaign_id: '', destination_url: '' })
  const [busy, setBusy] = useState(false)
  if (links.loading && !links.data) return <Spinner />
  if (links.error) return <ErrorBox message={links.error} onRetry={links.reload} />
  const items = links.data?.items || []
  const sourceName = (id: number) => sources.find((s) => s.id === id)?.name || '—'

  const create = async () => {
    setBusy(true)
    try {
      await partnerApi.createLink({ name: form.name || 'Link', source_id: Number(form.source_id), campaign_id: form.campaign_id ? Number(form.campaign_id) : undefined,
        destination_url: form.destination_url || undefined })
      setOpen(false)
      setForm({ name: '', source_id: '', campaign_id: '', destination_url: '' })
      onChange()
    } catch (e) { toastError(e) } finally { setBusy(false) }
  }

  return (
    <Card title="Tracking links" actions={<Btn small onClick={() => { setForm((f) => ({ ...f, source_id: String(sources[0]?.id || '') })); setOpen(true) }}><Plus className="h-4 w-4" />New link</Btn>}>
      {links.data?.mirrors?.length ? <p className="mb-3 text-[11px] text-slate-400">Mirror domains: {links.data.mirrors.join(', ')} — your codes work on every mirror.</p> : null}
      <div className="space-y-3">
        {items.map((link) => (
          <div key={link.id} className="rounded-xl border border-dark-border bg-dark-bg/50 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Link2 className="h-4 w-4 text-blue-300" />
              <span className="font-bold">{link.name}</span>
              <Badge status={link.status}>{link.status}</Badge>
              {link.is_default && <Badge tone="blue">Default</Badge>}
              <span className="text-[11px] text-slate-500">{sourceName(link.source_id)}</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg bg-dark-elevated px-2 py-2 text-xs text-blue-200">{link.urls.query}</code>
              <CopyButton text={link.urls.query || ''} />
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Btn tone="ghost" small onClick={() => setBuilder(link)}>Add sub-ids</Btn>
              <CopyButton text={link.urls.redirect || ''} label="/r/ link" />
              {!link.is_default && (
                <Btn tone="ghost" small onClick={async () => {
                  try { await partnerApi.updateLink(link.id, { status: link.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE' }); onChange() } catch (e) { toastError(e) }
                }}>{link.status === 'ACTIVE' ? 'Pause' : 'Activate'}</Btn>
              )}
            </div>
          </div>
        ))}
        {!items.length && <Empty />}
      </div>
      <Modal open={open} title="New tracking link" onClose={() => setOpen(false)}>
        <div className="space-y-3">
          <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="Telegram post 12 Oct" /></Field>
          <Field label="Source">
            <select value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value, campaign_id: '' })} className={inputCls}>
              {sources.filter((s) => s.status === 'ACTIVE').map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Campaign (optional)">
            <select value={form.campaign_id} onChange={(e) => setForm({ ...form, campaign_id: e.target.value })} className={inputCls}>
              <option value="">—</option>
              {campaigns.filter((c) => String(c.source_id) === form.source_id && c.status === 'ACTIVE').map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Landing page (optional)" hint="Leave empty to use the default sign-up page">
            <input value={form.destination_url} onChange={(e) => setForm({ ...form, destination_url: e.target.value })} className={inputCls} placeholder="https://" />
          </Field>
          <Btn className="w-full" busy={busy} disabled={!form.source_id} onClick={create}>Create link</Btn>
        </div>
      </Modal>
      {builder && <SubIdBuilder link={builder} onClose={() => setBuilder(null)} />}
    </Card>
  )
}

const SubIdBuilder: React.FC<{ link: TrackingLink; onClose: () => void }> = ({ link, onClose }) => {
  const [subs, setSubs] = useState({ sub1: '', sub2: '', sub3: '', sub4: '', sub5: '' })
  const url = withSubs(link.urls.query || '', subs)
  return (
    <Modal open title={`Sub-ids for ${link.name}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-slate-400">Sub-ids come back in your statistics (sub1) and in your postbacks ({'{sub1}'}…{'{sub5}'}).</p>
        {(Object.keys(subs) as Array<keyof typeof subs>).map((key) => (
          <Field key={key} label={key}><input value={subs[key]} maxLength={128} onChange={(e) => setSubs({ ...subs, [key]: e.target.value })} className={inputCls} /></Field>
        ))}
        <code className="block break-all rounded-lg bg-dark-elevated p-2 text-xs text-blue-200">{url}</code>
        <CopyButton text={url} label="Copy link" small={false} />
      </div>
    </Modal>
  )
}

const SourcesPanel: React.FC<{ state: Loaded<{ items: Source[] }>; onChange: () => void }> = ({ state, onChange }) => {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', type: 'TELEGRAM', url: '', description: '' })
  const [busy, setBusy] = useState(false)
  if (state.loading && !state.data) return <Spinner />
  if (state.error) return <ErrorBox message={state.error} onRetry={state.reload} />
  return (
    <Card title="Sources" actions={<Btn small onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New source</Btn>}>
      <div className="space-y-2">
        {(state.data?.items || []).map((s) => (
          <div key={s.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-dark-border p-3">
            <span className="font-bold">{s.name}</span>
            <Badge tone="blue">{s.type.replace('_', ' ')}</Badge>
            <Badge status={s.status}>{s.status}</Badge>
            {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="text-xs text-blue-300"><ExternalLink className="inline h-3 w-3" /> {s.url}</a>}
            {!s.is_default && (
              <Btn tone="ghost" small className="ml-auto" onClick={async () => {
                try { await partnerApi.updateSource(s.id, { status: s.status === 'ARCHIVED' ? 'ACTIVE' : 'ARCHIVED' }); onChange() } catch (e) { toastError(e) }
              }}>{s.status === 'ARCHIVED' ? 'Restore' : 'Archive'}</Btn>
            )}
          </div>
        ))}
      </div>
      <Modal open={open} title="New source" onClose={() => setOpen(false)}>
        <div className="space-y-3">
          <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} /></Field>
          <Field label="Type">
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className={inputCls}>
              {SOURCE_TYPES.map((x) => <option key={x} value={x}>{x.replace('_', ' ')}</option>)}
            </select>
          </Field>
          <Field label="URL"><input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className={inputCls} placeholder="https://t.me/…" /></Field>
          <Field label="Description"><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={cx(inputCls, 'py-2')} rows={2} /></Field>
          <Btn className="w-full" busy={busy} disabled={!form.name.trim()} onClick={async () => {
            setBusy(true)
            try { await partnerApi.createSource({ ...form, url: form.url || undefined }); setOpen(false); setForm({ name: '', type: 'TELEGRAM', url: '', description: '' }); onChange() } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Create</Btn>
        </div>
      </Modal>
    </Card>
  )
}

const CampaignsPanel: React.FC<{ state: Loaded<{ items: Campaign[] }>; sources: Source[]; onChange: () => void }> = ({ state, sources, onChange }) => {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', source_id: '', destination_url: '', blocked_countries: '' })
  const [busy, setBusy] = useState(false)
  if (state.loading && !state.data) return <Spinner />
  if (state.error) return <ErrorBox message={state.error} onRetry={state.reload} />
  return (
    <Card title="Campaigns" actions={<Btn small onClick={() => { setForm((f) => ({ ...f, source_id: String(sources[0]?.id || '') })); setOpen(true) }}><Plus className="h-4 w-4" />New campaign</Btn>}>
      <div className="space-y-2">
        {(state.data?.items || []).map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-dark-border p-3">
            <span className="font-bold">{c.name}</span>
            <Badge status={c.status}>{c.status}</Badge>
            <span className="text-[11px] text-slate-500">{sources.find((s) => s.id === c.source_id)?.name}</span>
            {c.blocked_countries.length > 0 && <span className="text-[11px] text-amber-300">Blocked: {c.blocked_countries.join(', ')}</span>}
            <Btn tone="ghost" small className="ml-auto" onClick={async () => {
              try { await partnerApi.updateCampaign(c.id, { status: c.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE' }); onChange() } catch (e) { toastError(e) }
            }}>{c.status === 'ACTIVE' ? 'Pause' : 'Activate'}</Btn>
          </div>
        ))}
        {!state.data?.items.length && <Empty>Campaigns group links of one source and can block countries.</Empty>}
      </div>
      <Modal open={open} title="New campaign" onClose={() => setOpen(false)}>
        <div className="space-y-3">
          <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} /></Field>
          <Field label="Source">
            <select value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value })} className={inputCls}>
              {sources.filter((s) => s.status === 'ACTIVE').map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Landing page (optional)"><input value={form.destination_url} onChange={(e) => setForm({ ...form, destination_url: e.target.value })} className={inputCls} placeholder="https://" /></Field>
          <Field label="Blocked countries" hint="Comma separated ISO codes, e.g. US, GB"><input value={form.blocked_countries} onChange={(e) => setForm({ ...form, blocked_countries: e.target.value })} className={cx(inputCls, 'uppercase')} /></Field>
          <Btn className="w-full" busy={busy} disabled={!form.name.trim() || !form.source_id} onClick={async () => {
            setBusy(true)
            try {
              await partnerApi.createCampaign({ name: form.name, source_id: Number(form.source_id), destination_url: form.destination_url || undefined,
                blocked_countries: form.blocked_countries.split(',').map((x) => x.trim().toUpperCase()).filter((x) => x.length === 2) })
              setOpen(false); onChange()
            } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Create</Btn>
        </div>
      </Modal>
    </Card>
  )
}

const PromoPanel: React.FC<{ state: Loaded<{ items: Array<{ id: number; tracking_link_id: number; code: string; status: string }> }>; links: TrackingLink[]; onChange: () => void }> = ({ state, links, onChange }) => {
  const [linkId, setLinkId] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  if (state.loading && !state.data) return <Spinner />
  return (
    <Card title="Promo codes">
      <p className="mb-3 text-xs text-slate-400">A promo code entered at sign-up attributes the player to you even without a click.</p>
      <div className="mb-4 flex flex-wrap gap-2">
        <select value={linkId} onChange={(e) => setLinkId(e.target.value)} className={cx(inputCls, 'w-auto flex-1')} aria-label="Link">
          <option value="">Choose a link…</option>
          {links.map((l) => <option key={l.id} value={l.id}>{l.name} · {l.link_code}</option>)}
        </select>
        <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CODE (optional)" maxLength={32} className={cx(inputCls, 'w-40 uppercase')} />
        <Btn busy={busy} disabled={!linkId} onClick={async () => {
          setBusy(true)
          try { await partnerApi.createPromo(Number(linkId), code || undefined); setCode(''); onChange() } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>Create</Btn>
      </div>
      <div className="flex flex-wrap gap-2">
        {(state.data?.items || []).map((p) => (
          <div key={p.id} className="flex items-center gap-2 rounded-xl border border-dark-border px-3 py-2">
            <code className="font-black tracking-wider">{p.code}</code><Badge status={p.status}>{p.status}</Badge><CopyButton text={p.code} />
          </div>
        ))}
        {!state.data?.items.length && <Empty />}
      </div>
    </Card>
  )
}

// ======================================================================= PR tools

export const PartnerPrTools: React.FC = () => {
  const t = useT()
  const [tab, setTab] = useState('BANNER')
  const materials = useAsync(() => partnerApi.materials(), [])
  const qrs = useAsync(() => partnerApi.qrCodes(), [])
  const links = useAsync(() => partnerApi.links(), [])
  const [linkId, setLinkId] = useState('')
  const [busy, setBusy] = useState(false)
  const items = useMemo(() => (materials.data?.items || []).filter((m) => m.type === tab), [materials.data, tab])
  const defaultLink = links.data?.items.find((l) => l.is_default)

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('prTools')}</h1>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'BANNER', label: 'Banners' }, { id: 'LANDING', label: 'Landings' }, { id: 'VIDEO', label: 'Videos' },
        { id: 'TEXT', label: 'Texts' }, { id: 'QR', label: 'QR codes' }]} />
      {tab !== 'QR' && (
        materials.loading && !materials.data ? <Spinner /> : (
          <div className="grid gap-3 sm:grid-cols-2">
            {items.map((m) => (
              <Card key={m.id} title={m.title} actions={<Badge tone="blue">{m.language.toUpperCase()}</Badge>}>
                {m.file_url && m.type === 'BANNER' && <img src={m.file_url} alt={m.title} className="mb-3 max-h-48 w-full rounded-lg object-contain bg-dark-bg" loading="lazy" />}
                {m.description && <p className="mb-2 text-xs text-slate-400">{m.description}</p>}
                {m.body_text && <p className="mb-2 whitespace-pre-wrap rounded-lg bg-dark-bg p-2 text-xs text-slate-200">{m.body_text}</p>}
                <div className="flex flex-wrap gap-2">
                  {m.body_text && <CopyButton text={m.body_text.replaceAll('{link}', defaultLink?.urls.query || '')} label="Copy text" />}
                  {m.file_url && <a href={m.file_url} target="_blank" rel="noreferrer" download className="inline-flex min-h-[36px] items-center gap-1 rounded-xl border border-dark-border px-3 text-xs font-bold text-slate-200"><Download className="h-3.5 w-3.5" />Open / download</a>}
                  {m.width && m.height && <span className="self-center text-[11px] text-slate-500">{m.width}×{m.height}</span>}
                  {m.geo.length > 0 && <span className="self-center text-[11px] text-slate-500">GEO: {m.geo.join(', ')}</span>}
                </div>
              </Card>
            ))}
            {!items.length && <Empty>No materials of this type yet.</Empty>}
          </div>
        )
      )}
      {tab === 'QR' && (
        <Card title="QR codes for your links">
          <div className="mb-4 flex flex-wrap gap-2">
            <select value={linkId} onChange={(e) => setLinkId(e.target.value)} className={cx(inputCls, 'w-auto flex-1')} aria-label="Link">
              <option value="">Choose a link…</option>
              {(links.data?.items || []).map((l) => <option key={l.id} value={l.id}>{l.name} · {l.link_code}</option>)}
            </select>
            <Btn busy={busy} disabled={!linkId} onClick={async () => {
              setBusy(true)
              try { await partnerApi.createQr(Number(linkId)); await qrs.reload(); showToast({ title: 'QR code ready', type: 'success' }) } catch (e) { toastError(e) } finally { setBusy(false) }
            }}><QrIcon className="h-4 w-4" />Create QR</Btn>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(qrs.data?.items || []).map((q) => (
              <a key={q.id} href={q.image_url} download={`qr-${q.name}`} className="rounded-xl border border-dark-border bg-white p-2 text-center">
                <img src={q.image_url} alt={q.name} className="mx-auto w-full" />
                <span className="text-[11px] font-bold text-slate-800">{q.name}</span>
              </a>
            ))}
          </div>
          {!qrs.data?.items.length && <Empty />}
        </Card>
      )}
      <p className="text-[11px] text-slate-500">Promote responsibly: 18+ only, never target minors, and keep the responsible-gambling message in your posts.</p>
    </div>
  )
}
