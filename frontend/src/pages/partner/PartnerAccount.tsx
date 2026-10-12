import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import {
  Badge, Btn, Card, Empty, Field, Modal, Spinner, Table, Td, dateTime, inputCls, toastError, useAsync,
} from '../../components/affiliate/ui'
import { showToast } from '../../components/common/Toast'
import { partnerApi } from '../../services/affiliate.api'
import { useAuthStore } from '../../store/auth.store'
import { useT } from './i18n'
import { usePartnerStore } from './partner.store'

const TIMEZONES = ['UTC', 'Asia/Kolkata', 'Asia/Dubai', 'Europe/London', 'Europe/Moscow', 'Asia/Dhaka', 'Asia/Karachi', 'Asia/Kathmandu',
  'Asia/Singapore', 'Africa/Lagos', 'America/Sao_Paulo', 'America/New_York']

export const PartnerProfile: React.FC = () => {
  const t = useT()
  const me = usePartnerStore((s) => s.me)
  const reload = usePartnerStore((s) => s.load)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const [profile, setProfile] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(me?.profile || {}).map(([k, v]) => [k, v || ''])))
  const [tz, setTz] = useState(me?.partner.timezone || 'UTC')
  const [busy, setBusy] = useState(false)
  const [pwd, setPwd] = useState({ current_password: '', new_password: '' })
  const [email, setEmail] = useState({ password: '', new_email: '' })
  if (!me) return <Spinner />

  const field = (key: string, label: string) => (
    <Field label={label} key={key}><input value={profile[key] || ''} onChange={(e) => setProfile({ ...profile, [key]: e.target.value })} className={inputCls} /></Field>
  )

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-black">{t('profile')}</h1>
      <Card title={t('Details')} actions={<Badge tone="blue">ID {me.partner.partner_code}</Badge>}>
        <div className="grid gap-3 sm:grid-cols-2">
          {field('first_name', t('First name'))}{field('last_name', t('Last name'))}{field('company_name', t('Company'))}{field('phone', t('Phone'))}
          {field('telegram', t('Telegram'))}{field('website', t('Website'))}{field('country', t('Country (2 letters)'))}{field('city', t('City'))}
          <Field label={t('Timezone (statistics days)')}>
            <select value={tz} onChange={(e) => setTz(e.target.value)} className={inputCls}>
              {[...new Set([tz, ...TIMEZONES])].map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </Field>
        </div>
        <Btn className="mt-4" busy={busy} onClick={async () => {
          setBusy(true)
          try {
            const clean = Object.fromEntries(Object.entries(profile).map(([k, v]) => [k, v.trim() || null]))
            if (clean.country) clean.country = String(clean.country).toUpperCase()
            await partnerApi.updateMe({ timezone: tz, profile: clean })
            showToast({ title: t('Saved'), type: 'success' })
            void reload()
          } catch (e) { toastError(e) } finally { setBusy(false) }
        }}>{t('save')}</Btn>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title={t('Change password')}>
          <div className="space-y-3">
            <Field label={t('Current password')}><input type="password" autoComplete="current-password" value={pwd.current_password} onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} className={inputCls} /></Field>
            <Field label={t('New password')} hint={t('At least 10 characters')}><input type="password" autoComplete="new-password" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} className={inputCls} /></Field>
            <Btn onClick={async () => {
              try {
                await partnerApi.changePassword(pwd)
                showToast({ title: t('Password changed'), message: t('Sign in again.'), type: 'success' })
                logout()
                navigate('/partner/login')
              } catch (e) { toastError(e) }
            }} disabled={!pwd.current_password || pwd.new_password.length < 10}>{t('Change password')}</Btn>
          </div>
        </Card>
        <Card title={t('Change email')}>
          <div className="space-y-3">
            <p className="text-xs text-slate-400">{t('Current: {email}', { email: me.partner.email || '—' })}</p>
            <Field label={t('New email')}><input type="email" value={email.new_email} onChange={(e) => setEmail({ ...email, new_email: e.target.value })} className={inputCls} /></Field>
            <Field label={t('Password')}><input type="password" value={email.password} onChange={(e) => setEmail({ ...email, password: e.target.value })} className={inputCls} /></Field>
            <Btn onClick={async () => {
              try { await partnerApi.changeEmail(email); showToast({ title: t('Check your new inbox to confirm it'), type: 'success' }); void reload() } catch (e) { toastError(e) }
            }} disabled={!email.new_email || !email.password}>{t('Change email')}</Btn>
          </div>
        </Card>
      </div>

      <Card title={t('Sessions')}>
        <p className="mb-3 text-xs text-slate-400">{t('Sign out everywhere if you used a shared device or suspect someone else has access.')}</p>
        <Btn tone="danger" onClick={async () => {
          try { await partnerApi.logoutAll(); logout(); navigate('/partner/login') } catch (e) { toastError(e) }
        }}>{t('Log out of all devices')}</Btn>
      </Card>

      <Postbacks />
    </div>
  )
}

const Postbacks: React.FC = () => {
  const t = useT()
  const data = useAsync(() => partnerApi.postbacks(), [])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ event_type: 'REGISTRATION', url_template: '' })
  const [busy, setBusy] = useState(false)
  const [test, setTest] = useState<string | null>(null)
  return (
    <Card title={t('Postbacks (for your own tracker)')} actions={<Btn small onClick={() => setOpen(true)}><Plus className="h-4 w-4" />{t('Add')}</Btn>}>
      <p className="mb-3 text-xs text-slate-400">{t('We call your URL on each event. Macros:')} {(data.data?.macros || []).map((m) => `{${m}}`).join(' ')}</p>
      {data.loading && !data.data ? <Spinner /> : (
        <div className="space-y-2">
          {(data.data?.items || []).map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-dark-border p-3 text-xs">
              <Badge tone="purple">{p.event_type}</Badge><Badge status={p.status}>{t(p.status)}</Badge>
              <code className="min-w-0 flex-1 truncate text-blue-200">{p.url_template}</code>
              <Btn tone="ghost" small onClick={async () => {
                try { const r = await partnerApi.testPostback(p.id); setTest(`${r.url} → ${r.status_code ?? r.error}`) } catch (e) { toastError(e) }
              }}>{t('Test')}</Btn>
              <Btn tone="ghost" small onClick={async () => { try { await partnerApi.updatePostback(p.id, { status: p.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE' }); void data.reload() } catch (e) { toastError(e) } }}>
                {p.status === 'ACTIVE' ? t('Pause') : t('Activate')}
              </Btn>
            </div>
          ))}
          {!data.data?.items.length && <Empty>{t('No postbacks')}</Empty>}
          {test && <p className="break-all rounded-lg bg-dark-bg p-2 text-[11px] text-slate-300">{test}</p>}
          {(data.data?.logs.length ?? 0) > 0 && (
            <Table head={[t('Sent'), t('Event'), t('Status'), t('Code'), t('Attempts')]}>
              {data.data!.logs.slice(0, 20).map((l) => (
                <tr key={l.id}><Td>{dateTime(l.sent_at || l.created_at)}</Td><Td>{l.event_ref}</Td><Td><Badge status={l.status}>{t(l.status)}</Badge></Td><Td>{l.response_code ?? '—'}</Td><Td>{l.attempts}</Td></tr>
              ))}
            </Table>
          )}
        </div>
      )}
      <Modal open={open} title={t('Add postback')} onClose={() => setOpen(false)}>
        <div className="space-y-3">
          <Field label={t('Event')}>
            <select value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })} className={inputCls}>
              <option value="REGISTRATION">{t('Registration')}</option><option value="FTD">{t('First deposit')}</option><option value="DEPOSIT">{t('Every deposit')}</option>
            </select>
          </Field>
          <Field label="URL" hint="https://tracker.example.com/postback?clickid={click_id}&payout={amount}">
            <input value={form.url_template} onChange={(e) => setForm({ ...form, url_template: e.target.value })} className={inputCls} />
          </Field>
          <Btn className="w-full" busy={busy} onClick={async () => {
            setBusy(true)
            try { await partnerApi.createPostback(form.event_type, form.url_template); setOpen(false); void data.reload() } catch (e) { toastError(e) } finally { setBusy(false) }
          }}>{t('Save')}</Btn>
        </div>
      </Modal>
    </Card>
  )
}

