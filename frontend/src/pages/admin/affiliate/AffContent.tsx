import React, { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import {
  Badge, Btn, Card, Field, Modal, Spinner, Table, Tabs, Td, cx, dateTime, inputCls, toastError, useAsync,
} from '../../../components/affiliate/ui'
import { showToast } from '../../../components/common/Toast'
import { usePermission } from '../../../hooks/usePermission'
import { affAdminApi } from '../../../services/affiliateAdmin.api'
import type { BlogPost, Contact, Faq, PrMaterial } from '../../../types/affiliate.types'

const readFile = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result))
  reader.onerror = reject
  reader.readAsDataURL(file)
})

export const AffContentAdmin: React.FC = () => {
  const { hasPermission } = usePermission()
  const tabs = [
    hasPermission('aff:content:manage') && { id: 'pr', label: 'PR materials' },
    hasPermission('aff:content:manage') && { id: 'blog', label: 'Blog' },
    hasPermission('aff:support:manage') && { id: 'faq', label: 'FAQ' },
    hasPermission('aff:support:manage') && { id: 'contacts', label: 'Contacts' },
  ].filter(Boolean) as Array<{ id: string; label: string }>
  const [tab, setTab] = useState(tabs[0]?.id || 'faq')
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Partner content & support</h1>
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === 'pr' && <Materials />}
      {tab === 'blog' && <Blog />}
      {tab === 'faq' && <Faqs />}
      {tab === 'contacts' && <Contacts />}
    </div>
  )
}

const emptyMaterial = { type: 'BANNER', title: '', description: '', file_url: '', body_text: '', width: '', height: '', language: 'en', geo: '', status: 'DRAFT' }

const Materials: React.FC = () => {
  const data = useAsync(() => affAdminApi.materials(), [])
  const [edit, setEdit] = useState<(typeof emptyMaterial & { id?: number }) | null>(null)
  const [busy, setBusy] = useState(false)
  const toForm = (m: PrMaterial) => ({ ...emptyMaterial, ...m, description: m.description || '', file_url: m.file_url || '', body_text: m.body_text || '',
    width: m.width ? String(m.width) : '', height: m.height ? String(m.height) : '', geo: m.geo.join(', ') })
  return (
    <Card actions={<Btn small onClick={() => setEdit({ ...emptyMaterial })}><Plus className="h-4 w-4" />New material</Btn>}>
      <p className="mb-3 text-xs text-slate-400">Publishing a material is the compliance review: check 18+ and responsible-gambling wording first. Use {'{link}'} in texts for the partner's link.</p>
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={['Title', 'Type', 'Lang', 'GEO', 'Status', '']} empty={!data.data?.items.length}>
          {(data.data?.items || []).map((m) => (
            <tr key={m.id}><Td className="font-bold">{m.title}</Td><Td>{m.type}</Td><Td>{m.language}</Td><Td>{m.geo.join(', ') || 'all'}</Td>
              <Td><Badge status={m.status}>{m.status}</Badge></Td><Td><Btn tone="ghost" small onClick={() => setEdit(toForm(m))}>Edit</Btn></Td></tr>
          ))}
        </Table>
      )}
      <Modal open={edit !== null} title={edit?.id ? 'Edit material' : 'New material'} onClose={() => setEdit(null)} wide>
        {edit && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type"><select value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })} className={inputCls}>{['BANNER', 'LANDING', 'VIDEO', 'TEXT'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Field label="Title"><input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} className={inputCls} /></Field>
            <Field label="File / URL" hint="https:// link, or upload an image under 2 MB" className="sm:col-span-2">
              <div className="flex gap-2">
                <input value={edit.file_url.startsWith('data:') ? '(uploaded image)' : edit.file_url} onChange={(e) => setEdit({ ...edit, file_url: e.target.value })} className={inputCls} />
                <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="w-40 text-xs" onChange={async (e) => {
                  const f = e.target.files?.[0]
                  if (f) {
                    const url = await readFile(f)
                    const img = new Image()
                    img.onload = () => setEdit((cur) => cur && { ...cur, file_url: url, width: String(img.width), height: String(img.height) })
                    img.src = url
                  }
                }} />
              </div>
            </Field>
            <Field label="Text" className="sm:col-span-2"><textarea value={edit.body_text} onChange={(e) => setEdit({ ...edit, body_text: e.target.value })} rows={3} className={cx(inputCls, 'py-2')} /></Field>
            <Field label="Description"><input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} className={inputCls} /></Field>
            <Field label="Language"><input value={edit.language} onChange={(e) => setEdit({ ...edit, language: e.target.value })} className={inputCls} /></Field>
            <Field label="Width × height"><div className="flex gap-2"><input value={edit.width} onChange={(e) => setEdit({ ...edit, width: e.target.value })} className={inputCls} /><input value={edit.height} onChange={(e) => setEdit({ ...edit, height: e.target.value })} className={inputCls} /></div></Field>
            <Field label="GEO (empty = all)"><input value={edit.geo} onChange={(e) => setEdit({ ...edit, geo: e.target.value })} className={inputCls} placeholder="IN, BD" /></Field>
            <Field label="Status"><select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })} className={inputCls}>{['DRAFT', 'PUBLISHED', 'ARCHIVED'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Btn className="sm:col-span-2" busy={busy} disabled={!edit.title} onClick={async () => {
              setBusy(true)
              try {
                const body = { ...edit, width: edit.width ? Number(edit.width) : null, height: edit.height ? Number(edit.height) : null,
                  geo: edit.geo.split(',').map((x) => x.trim()).filter(Boolean), file_url: edit.file_url || null, description: edit.description || null, body_text: edit.body_text || null }
                delete (body as { id?: number }).id
                if (edit.id) await affAdminApi.updateMaterial(edit.id, body); else await affAdminApi.createMaterial(body)
                setEdit(null); void data.reload()
              } catch (e) { toastError(e) } finally { setBusy(false) }
            }}>Save</Btn>
          </div>
        )}
      </Modal>
    </Card>
  )
}

const Blog: React.FC = () => {
  const data = useAsync(() => affAdminApi.blog(), [])
  const [edit, setEdit] = useState<(Partial<BlogPost> & { content: string; status: string }) | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <Card actions={<Btn small onClick={() => setEdit({ title: '', excerpt: '', content: '', cover_image: '', language: 'en', status: 'DRAFT' })}><Plus className="h-4 w-4" />New post</Btn>}>
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={['Title', 'Status', 'Published', '']} empty={!data.data?.items.length}>
          {(data.data?.items || []).map((b) => (
            <tr key={b.id}><Td className="font-bold">{b.title}</Td><Td><Badge status={b.status}>{b.status}</Badge></Td><Td>{dateTime(b.published_at)}</Td>
              <Td><Btn tone="ghost" small onClick={() => setEdit({ ...b, content: b.content || '' })}>Edit</Btn></Td></tr>
          ))}
        </Table>
      )}
      <Modal open={edit !== null} title={edit?.id ? 'Edit post' : 'New post'} onClose={() => setEdit(null)} wide>
        {edit && (
          <div className="space-y-3">
            <Field label="Title"><input value={edit.title || ''} onChange={(e) => setEdit({ ...edit, title: e.target.value })} className={inputCls} /></Field>
            <Field label="Excerpt"><input value={edit.excerpt || ''} onChange={(e) => setEdit({ ...edit, excerpt: e.target.value })} className={inputCls} /></Field>
            <Field label="Cover image URL"><input value={edit.cover_image || ''} onChange={(e) => setEdit({ ...edit, cover_image: e.target.value })} className={inputCls} /></Field>
            <Field label="Content"><textarea value={edit.content} onChange={(e) => setEdit({ ...edit, content: e.target.value })} rows={10} className={cx(inputCls, 'py-2')} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Language"><input value={edit.language || 'en'} onChange={(e) => setEdit({ ...edit, language: e.target.value })} className={inputCls} /></Field>
              <Field label="Status"><select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })} className={inputCls}>{['DRAFT', 'PUBLISHED', 'ARCHIVED'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            </div>
            <Btn className="w-full" busy={busy} onClick={async () => {
              setBusy(true)
              try {
                const body = { title: edit.title, excerpt: edit.excerpt || null, content: edit.content, cover_image: edit.cover_image || null, language: edit.language || 'en', status: edit.status }
                if (edit.id) await affAdminApi.updateBlog(edit.id, body); else await affAdminApi.createBlog(body)
                setEdit(null); void data.reload()
              } catch (e) { toastError(e) } finally { setBusy(false) }
            }}>Save</Btn>
          </div>
        )}
      </Modal>
    </Card>
  )
}

const Faqs: React.FC = () => {
  const data = useAsync(() => affAdminApi.faqs(), [])
  const [edit, setEdit] = useState<(Partial<Faq> & { question: string; answer: string }) | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <Card actions={<Btn small onClick={() => setEdit({ question: '', answer: '', category: 'General', language: 'en', status: 'PUBLISHED', sort_order: 0 })}><Plus className="h-4 w-4" />New question</Btn>}>
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={['#', 'Question', 'Category', 'Lang', 'Status', '']} empty={!data.data?.items.length}>
          {(data.data?.items || []).map((f) => (
            <tr key={f.id}><Td>{f.sort_order}</Td><Td className="max-w-[360px] whitespace-normal font-bold">{f.question}</Td><Td>{f.category}</Td><Td>{f.language}</Td>
              <Td><Badge status={f.status}>{f.status}</Badge></Td><Td><Btn tone="ghost" small onClick={() => setEdit(f)}>Edit</Btn></Td></tr>
          ))}
        </Table>
      )}
      <Modal open={edit !== null} title="FAQ" onClose={() => setEdit(null)}>
        {edit && (
          <div className="space-y-3">
            <Field label="Question"><input value={edit.question} onChange={(e) => setEdit({ ...edit, question: e.target.value })} className={inputCls} /></Field>
            <Field label="Answer"><textarea value={edit.answer} onChange={(e) => setEdit({ ...edit, answer: e.target.value })} rows={5} className={cx(inputCls, 'py-2')} /></Field>
            <div className="grid grid-cols-3 gap-2">
              <Field label="Category"><input value={edit.category || ''} onChange={(e) => setEdit({ ...edit, category: e.target.value })} className={inputCls} /></Field>
              <Field label="Lang"><input value={edit.language || 'en'} onChange={(e) => setEdit({ ...edit, language: e.target.value })} className={inputCls} /></Field>
              <Field label="Order"><input value={edit.sort_order ?? 0} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) || 0 })} className={inputCls} /></Field>
            </div>
            <Field label="Status"><select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })} className={inputCls}>{['PUBLISHED', 'DRAFT', 'ARCHIVED'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Btn className="w-full" busy={busy} onClick={async () => {
              setBusy(true)
              try {
                const body = { question: edit.question, answer: edit.answer, category: edit.category || null, language: edit.language || 'en', status: edit.status || 'PUBLISHED', sort_order: edit.sort_order || 0 }
                if (edit.id) await affAdminApi.updateFaq(edit.id, body); else await affAdminApi.createFaq(body)
                setEdit(null); void data.reload()
              } catch (e) { toastError(e) } finally { setBusy(false) }
            }}>Save</Btn>
          </div>
        )}
      </Modal>
    </Card>
  )
}

const Contacts: React.FC = () => {
  const [status, setStatus] = useState('NEW')
  const data = useAsync(() => affAdminApi.contacts(status || undefined), [status])
  const [open, setOpen] = useState<Contact | null>(null)
  const [reply, setReply] = useState('')
  useEffect(() => setReply(open?.reply || ''), [open])
  return (
    <Card>
      <div className="mb-3"><Tabs value={status} onChange={setStatus} tabs={[{ id: 'NEW', label: 'New' }, { id: 'IN_PROGRESS', label: 'In progress' }, { id: 'CLOSED', label: 'Closed' }, { id: '', label: 'All' }]} /></div>
      {data.loading && !data.data ? <Spinner /> : (
        <Table head={['When', 'Partner', 'Subject', 'Status', '']} empty={!data.data?.items.length}>
          {(data.data?.items || []).map((c) => (
            <tr key={c.id}><Td>{dateTime(c.created_at)}</Td><Td>{c.partner_code || c.email}</Td><Td className="font-bold">{c.subject}</Td>
              <Td><Badge status={c.status}>{c.status}</Badge></Td><Td><Btn tone="ghost" small onClick={() => setOpen(c)}>Open</Btn></Td></tr>
          ))}
        </Table>
      )}
      <Modal open={open !== null} title={open?.subject || ''} onClose={() => setOpen(null)}>
        {open && (
          <div className="space-y-3">
            <p className="text-xs text-slate-400">{open.name} · {open.email}</p>
            <p className="whitespace-pre-wrap rounded-xl bg-dark-bg p-3 text-sm">{open.message}</p>
            <Field label="Reply (sent to the partner as a notification)"><textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={4} className={cx(inputCls, 'py-2')} /></Field>
            <div className="flex gap-2">
              <Btn className="flex-1" onClick={async () => { try { await affAdminApi.replyContact(open.id, { reply }); setOpen(null); void data.reload() } catch (e) { toastError(e) } }} disabled={!reply.trim()}>Send reply</Btn>
              <Btn tone="ghost" onClick={async () => { try { await affAdminApi.replyContact(open.id, { status: 'CLOSED' }); setOpen(null); void data.reload() } catch (e) { toastError(e) } }}>Close</Btn>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  )
}

// ============================================================ settings & terms

const SETTING_LABELS: Record<string, string> = {
  min_payout: 'Minimum payout ($)', withdrawal_fee: 'Withdrawal fee ($)', method_cooldown_hours: 'Payout method cool-down (hours)',
  default_hold_days: 'CPA hold for new deals (days)', cookie_days: 'Tracking cookie (days)', attribution_window_days: 'Attribution window (days)',
  settlement_period_type: 'Settlement period', default_subpartner_rate: 'Default subpartner share (0.05 = 5%)', subpartner_depth: 'Subpartner levels (0/1)',
  default_plan_id: 'Plan for self sign-ups (id, 0 = first)', auto_approve_signups: 'Auto-approve sign-ups', default_destination_url: 'Default landing URL',
  blocked_geo_url: 'Blocked-country redirect URL', bot_clicks_per_minute: 'Bot threshold (clicks / IP / minute)', unique_click_window_hours: 'Unique click window (hours)',
  app_android_url: 'Android app URL', app_ios_url: 'iOS app URL', languages: 'Portal languages', fallback_fx_rates: 'Fallback FX rates (JSON)',
  terms_required: 'Require latest terms', auto_close_periods: 'Close ended periods automatically',
}

export const AffSettings: React.FC = () => {
  const { isSuperAdmin } = usePermission()
  const [tab, setTab] = useState('settings')
  const data = useAsync(() => affAdminApi.settings(), [])
  const terms = useAsync(() => affAdminApi.terms(), [])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [newTerms, setNewTerms] = useState({ version: '', content: '' })
  useEffect(() => {
    if (data.data) setDraft(Object.fromEntries(Object.entries(data.data.values).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])))
  }, [data.data])
  if (data.loading && !data.data) return <Spinner />
  const values = data.data?.values || {}
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-black">Affiliate settings</h1>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'settings', label: 'Global settings' }, { id: 'terms', label: 'Partner terms' }]} />
      {tab === 'settings' && (
        <Card>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.keys(values).map((key) => {
              const v = values[key]
              return (
                <Field key={key} label={SETTING_LABELS[key] || key} hint={data.data?.descriptions[key]}>
                  {typeof v === 'boolean' ? (
                    <select value={draft[key]} disabled={!isSuperAdmin()} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className={inputCls}><option value="true">On</option><option value="false">Off</option></select>
                  ) : key === 'settlement_period_type' ? (
                    <select value={draft[key]} disabled={!isSuperAdmin()} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className={inputCls}><option>WEEKLY</option><option>MONTHLY</option></select>
                  ) : (
                    <input value={draft[key] ?? ''} disabled={!isSuperAdmin()} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className={inputCls} />
                  )}
                </Field>
              )
            })}
          </div>
          {isSuperAdmin() && <Btn className="mt-4" busy={busy} onClick={async () => {
            setBusy(true)
            try {
              const changes: Record<string, unknown> = {}
              for (const [key, raw] of Object.entries(draft)) {
                const original = values[key]
                const current = typeof original === 'object' ? JSON.stringify(original) : String(original)
                if (raw === current) continue
                changes[key] = typeof original === 'boolean' ? raw === 'true' : typeof original === 'object' ? JSON.parse(raw) : raw
              }
              if (Object.keys(changes).length) { await affAdminApi.saveSettings(changes); showToast({ title: 'Settings saved', type: 'success' }); void data.reload() }
            } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>Save changes</Btn>}
        </Card>
      )}
      {tab === 'terms' && (
        <>
          {isSuperAdmin() && (
            <Card title="Publish a new version">
              <p className="mb-3 text-xs text-amber-300">Partners must accept a new version before using the portal. Get legal sign-off for your target markets first.</p>
              <div className="space-y-3">
                <Field label="Version"><input value={newTerms.version} onChange={(e) => setNewTerms({ ...newTerms, version: e.target.value })} className={inputCls} placeholder="1.0" /></Field>
                <Field label="Terms text"><textarea value={newTerms.content} onChange={(e) => setNewTerms({ ...newTerms, content: e.target.value })} rows={10} className={cx(inputCls, 'py-2')} /></Field>
                <Btn disabled={!newTerms.version || newTerms.content.length < 10} onClick={async () => {
                  try { await affAdminApi.publishTerms(newTerms); setNewTerms({ version: '', content: '' }); void terms.reload() } catch (e) { toastError(e) }
                }}>Publish</Btn>
              </div>
            </Card>
          )}
          <Card title="Versions">
            <Table head={['Version', 'Published']} empty={!terms.data?.items.length}>
              {(terms.data?.items || []).map((t) => <tr key={t.id}><Td className="font-bold">{t.version}</Td><Td>{dateTime(t.published_at)}</Td></tr>)}
            </Table>
          </Card>
        </>
      )}
    </div>
  )
}
