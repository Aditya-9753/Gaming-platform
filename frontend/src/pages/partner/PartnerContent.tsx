import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronDown, Mail, Send, UserRound } from 'lucide-react'
import { Badge, Btn, Card, Empty, ErrorBox, Field, Spinner, cx, dateOnly, dateTime, inputCls, toastError, useAsync } from '../../components/affiliate/ui'
import { showToast } from '../../components/common/Toast'
import { partnerApi } from '../../services/affiliate.api'
import { useT } from './i18n'
import { usePartnerStore } from './partner.store'

export const PartnerFaq: React.FC = () => {
  const t = useT()
  const locale = usePartnerStore((s) => s.locale)
  const data = useAsync(() => partnerApi.faqs(), [])
  const [open, setOpen] = useState<number | null>(null)
  if (data.loading && !data.data) return <Spinner />
  if (data.error) return <ErrorBox message={data.error} onRetry={data.reload} />
  const all = data.data?.items || []
  const items = all.some((f) => f.language === locale) ? all.filter((f) => f.language === locale) : all.filter((f) => f.language === 'en')
  const groups = items.reduce<Record<string, typeof items>>((acc, f) => ((acc[f.category || 'General'] ||= []).push(f), acc), {})
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('faq')}</h1>
      {!items.length && <Empty />}
      {Object.entries(groups).map(([group, list]) => (
        <Card key={group} title={group}>
          <div className="divide-y divide-dark-border">
            {list.map((f) => (
              <div key={f.id}>
                <button type="button" onClick={() => setOpen(open === f.id ? null : f.id)} aria-expanded={open === f.id}
                  className="flex min-h-[48px] w-full items-center justify-between gap-3 py-2 text-left text-sm font-bold">
                  {f.question}<ChevronDown className={cx('h-4 w-4 shrink-0 transition', open === f.id && 'rotate-180')} />
                </button>
                {open === f.id && <p className="whitespace-pre-wrap pb-3 text-sm text-slate-300">{f.answer}</p>}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}

export const PartnerContacts: React.FC = () => {
  const t = useT()
  const me = usePartnerStore((s) => s.me)
  const manager = useAsync(() => partnerApi.manager(), [])
  const history = useAsync(() => partnerApi.contacts(), [])
  const [form, setForm] = useState({ subject: '', message: '' })
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('contacts')}</h1>
      <Card title="Your manager">
        {manager.loading ? <Spinner /> : manager.data?.manager ? (
          <div className="flex items-center gap-3">
            <UserRound className="h-10 w-10 rounded-full bg-dark-elevated p-2 text-blue-300" />
            <div>
              <div className="font-bold">{manager.data.manager.name}</div>
              {manager.data.manager.email && <a href={`mailto:${manager.data.manager.email}`} className="text-xs text-blue-300"><Mail className="inline h-3 w-3" /> {manager.data.manager.email}</a>}
            </div>
          </div>
        ) : <p className="text-sm text-slate-400">A manager will be assigned to you soon. Meanwhile, write to us below.</p>}
      </Card>
      <Card title="Send a message">
        <div className="space-y-3">
          <Field label="Subject"><input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} maxLength={200} className={inputCls} /></Field>
          <Field label="Message"><textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} rows={4} maxLength={5000} className={cx(inputCls, 'py-2')} /></Field>
          <Btn busy={busy} disabled={!form.subject.trim() || !form.message.trim()} onClick={async () => {
            setBusy(true)
            try {
              await partnerApi.sendContact({ name: me?.name || 'Partner', email: me?.partner.email || '', ...form })
              showToast({ title: 'Message sent', type: 'success' })
              setForm({ subject: '', message: '' })
              void history.reload()
            } catch (e) { toastError(e) } finally { setBusy(false) }
          }}><Send className="h-4 w-4" />Send</Btn>
        </div>
      </Card>
      {(history.data?.items.length ?? 0) > 0 && (
        <Card title="Your messages">
          <div className="space-y-3">
            {history.data!.items.map((c) => (
              <div key={c.id} className="rounded-xl border border-dark-border p-3 text-sm">
                <div className="mb-1 flex items-center gap-2"><span className="font-bold">{c.subject}</span><Badge status={c.status}>{c.status.replace('_', ' ')}</Badge>
                  <span className="ml-auto text-[11px] text-slate-500">{dateTime(c.created_at)}</span></div>
                <p className="whitespace-pre-wrap text-slate-400">{c.message}</p>
                {c.reply && <p className="mt-2 whitespace-pre-wrap rounded-lg bg-blue-500/10 p-2 text-blue-100">{c.reply}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

export const PartnerBlog: React.FC = () => {
  const t = useT()
  const data = useAsync(() => partnerApi.blog(), [])
  if (data.loading && !data.data) return <Spinner />
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('blog')}</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        {(data.data?.items || []).map((p) => (
          <Link key={p.id} to={`/partner/blog/${p.slug}`} className="overflow-hidden rounded-2xl border border-dark-border bg-dark-card hover:border-brand-blue/50">
            {p.cover_image && <img src={p.cover_image} alt="" className="h-36 w-full object-cover" loading="lazy" />}
            <div className="p-4">
              <div className="text-[11px] text-slate-500">{dateOnly(p.published_at)}</div>
              <div className="font-black">{p.title}</div>
              {p.excerpt && <p className="mt-1 line-clamp-2 text-xs text-slate-400">{p.excerpt}</p>}
            </div>
          </Link>
        ))}
      </div>
      {!data.data?.items.length && <Empty>No posts yet</Empty>}
    </div>
  )
}

export const PartnerBlogPost: React.FC = () => {
  const { slug = '' } = useParams()
  const data = useAsync(() => partnerApi.blogPost(slug), [slug])
  if (data.loading && !data.data) return <Spinner />
  if (data.error) return <ErrorBox message={data.error} />
  const p = data.data!
  return (
    <article className="space-y-4">
      <Link to="/partner/blog" className="text-xs text-blue-300">← Blog</Link>
      {p.cover_image && <img src={p.cover_image} alt="" className="max-h-72 w-full rounded-2xl object-cover" />}
      <div className="text-[11px] text-slate-500">{dateOnly(p.published_at)}</div>
      <h1 className="text-2xl font-black">{p.title}</h1>
      <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{p.content}</div>
    </article>
  )
}

export const PartnerNotifications: React.FC = () => {
  const t = useT()
  const reloadMe = usePartnerStore((s) => s.load)
  const data = useAsync(() => partnerApi.notifications(), [])
  const items = data.data?.items || []
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-black">{t('notifications')}</h1>
        {items.some((n) => !n.is_read) && (
          <Btn tone="ghost" small onClick={async () => { try { await partnerApi.readNotifications(); await data.reload(); void reloadMe() } catch (e) { toastError(e) } }}>
            Mark all read
          </Btn>
        )}
      </div>
      {data.loading && !data.data ? <Spinner /> : (
        <div className="space-y-2">
          {items.map((n) => (
            <div key={n.id} className={cx('rounded-2xl border p-3', n.is_read ? 'border-dark-border bg-dark-card' : 'border-brand-blue/40 bg-brand-blue/10')}>
              <div className="flex items-center gap-2">
                <span className="font-bold">{n.title}</span>
                {n.type === 'SECURITY' && <Badge tone="red">Security</Badge>}
                <span className="ml-auto text-[11px] text-slate-500">{dateTime(n.created_at)}</span>
              </div>
              <p className="mt-1 text-sm text-slate-300">{n.message}</p>
            </div>
          ))}
          {!items.length && <Empty>{t('noData')}</Empty>}
        </div>
      )}
    </div>
  )
}
