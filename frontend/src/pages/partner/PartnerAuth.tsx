import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { Eye, EyeOff, Lock, Mail } from 'lucide-react'
import { BrandHero } from '../../components/brand/BrandHero'
import { useLogoSplash } from '../../components/brand/logoSplashStore'
import { Turnstile } from '../../components/common/Turnstile'
import { captchaSiteKey } from '../../components/common/captcha'
import { Btn, Field, inputCls } from '../../components/affiliate/ui'
import { cx, errorText } from '../../components/affiliate/helpers'
import { authApi } from '../../services/auth.api'
import { partnerApi } from '../../services/affiliate.api'
import { useAuthStore } from '../../store/auth.store'
import { useUIStore } from '../../store/ui.store'
import { impersonation } from '../../utils/impersonation'
import { LANGUAGE_NAMES, useT } from './i18n'
import { usePartnerStore } from './partner.store'

const Shell: React.FC<{ title: string; subtitle?: string; children: React.ReactNode }> = ({ title, subtitle, children }) => {
  const t = useT()
  const locale = usePartnerStore((s) => s.locale)
  const setLocale = usePartnerStore((s) => s.setLocale)
  return (
    <div className="dark flex min-h-[100dvh] items-start justify-center bg-dark-bg px-4 py-8 text-white sm:items-center">
      <div className="rw-rise w-full max-w-md space-y-5 rounded-3xl border border-dark-border bg-dark-card p-6 shadow-2xl sm:p-8">
        <div className="flex justify-end gap-1" role="group" aria-label={t('language')}>
          {(['en', 'hi'] as const).map((lang) => (
            <button key={lang} type="button" onClick={() => setLocale(lang)} aria-pressed={locale === lang}
              className={cx('min-h-[32px] rounded-lg px-2.5 text-[11px] font-black', locale === lang ? 'bg-brand-blue text-white' : 'bg-dark-elevated text-slate-300')}>
              {LANGUAGE_NAMES[lang]}
            </button>
          ))}
        </div>
        <div className="space-y-1 text-center">
          <BrandHero className="w-36 sm:w-40" />
          <div className="text-[11px] font-black uppercase tracking-[0.2em] text-blue-300">{t('Partners')}</div>
          <h1 className="pt-2 text-xl font-black">{title}</h1>
          {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
        </div>
        {children}
      </div>
    </div>
  )
}

const PasswordInput: React.FC<{ value: string; onChange: (v: string) => void; autoComplete: string; label?: string }> = ({ value, onChange, autoComplete, label }) => {
  const t = useT()
  const [show, setShow] = useState(false)
  return (
    <Field label={label ?? t('Password')}>
      <div className="relative">
        <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input type={show ? 'text' : 'password'} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={autoComplete} required
          className={cx(inputCls, 'pl-9 pr-11')} />
        <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? t('Hide password') : t('Show password')}
          className="absolute right-1 top-1/2 -translate-y-1/2 rounded-lg p-2.5 text-slate-400 hover:text-white">
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </Field>
  )
}

export const PartnerLogin: React.FC = () => {
  const t = useT()
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [siteKey, setSiteKey] = useState<string | null>(null)
  const [captcha, setCaptcha] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { access_token } = await authApi.login(email.trim().toLowerCase(), password, undefined, captcha)
      setAccessToken(access_token)
      const user = await authApi.getCurrentUser()
      setAuth(user, access_token)
      useLogoSplash.getState().show()
      navigate(user.role === 'partner' ? '/partner/dashboard' : user.role === 'user' ? '/dashboard' : '/admin/dashboard', { replace: true })
    } catch (err) {
      const key = captchaSiteKey(err)
      if (key) {
        setSiteKey(key)
        setCaptcha(null)
        setError(errorText(err, t('Complete the captcha to continue')))
        return
      }
      // Generic text: never reveal whether the email exists
      setError(axios.isAxiosError(err) && err.response?.status === 401 ? t('Email or password incorrect') : errorText(err, t('Could not sign in')))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title={t('Sign in')} subtitle={t('Partner account')}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t('Email')}>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required className={cx(inputCls, 'pl-9')} />
          </div>
        </Field>
        <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" />
        {siteKey && <Turnstile siteKey={siteKey} onToken={setCaptcha} />}
        {error && <p className="rounded-xl bg-rose-500/10 p-3 text-xs text-rose-300" role="alert">{error}</p>}
        <Btn type="submit" busy={busy} disabled={Boolean(siteKey) && !captcha} className="w-full">{t('Sign in')}</Btn>
      </form>
      <div className="flex justify-between text-xs">
        <Link to="/forgot-password" className="text-blue-300 hover:underline">{t('Forgot password?')}</Link>
        <Link to="/partner/signup" className="font-bold text-blue-300 hover:underline">{t('Sign up')}</Link>
      </div>
    </Shell>
  )
}

const CHECKS: Array<[string, (p: string) => boolean]> = [
  ['At least 10 characters', (p) => p.length >= 10],
  ['Not a common password', (p) => new Set(p).size >= 4],
]

export const PartnerSignup: React.FC = () => {
  const t = useT()
  const [params] = useSearchParams()
  const inviter = params.get('inviter') || ''
  const [inviterOk, setInviterOk] = useState<boolean | null>(null)
  const [terms, setTerms] = useState<{ id: number; version: string } | null>(null)
  const [form, setForm] = useState({ email: '', password: '', first_name: '', last_name: '', country: '', telegram: '', website: '', traffic_description: '' })
  const [accept, setAccept] = useState(false)
  const [adult, setAdult] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ status: string } | null>(null)

  useEffect(() => {
    partnerApi.config().then((c) => setTerms(c.terms)).catch(() => setTerms(null))
    if (inviter) partnerApi.inviter(inviter).then((r) => setInviterOk(r.valid)).catch(() => setInviterOk(false))
  }, [inviter])

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await partnerApi.signup({
        email: form.email.trim().toLowerCase(), password: form.password, accept_terms: accept, confirm_adult: adult,
        inviter: inviter && inviterOk ? inviter : undefined, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        locale: useUIStore.getState().locale,
        profile: {
          first_name: form.first_name || undefined, last_name: form.last_name || undefined, country: form.country ? form.country.toUpperCase() : undefined,
          telegram: form.telegram || undefined, website: form.website || undefined, traffic_description: form.traffic_description || undefined,
        },
      })
      setDone({ status: res.status })
    } catch (err) {
      setError(errorText(err, t('Could not create the account')))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <Shell title={t('Check your email')} subtitle={t('One more step')}>
        <p className="text-center text-sm text-slate-300">{t('We sent a confirmation link to')} <b>{form.email}</b>.
          {done.status === 'PENDING' ? t(' After you confirm it, our team reviews your application.') : t(' Confirm it to start.')}</p>
        <Link to="/partner/login" className="block text-center text-sm font-bold text-blue-300 underline">{t('Go to sign in')}</Link>
      </Shell>
    )
  }

  return (
    <Shell title={t('Become a partner')} subtitle={t('Earn a share of what your players generate')}>
      {inviter && inviterOk === true && <p className="rounded-xl bg-emerald-500/10 p-3 text-xs text-emerald-200">{t('Invited by partner {code}', { code: inviter })}</p>}
      {inviter && inviterOk === false && <p className="rounded-xl bg-amber-500/10 p-3 text-xs text-amber-200">{t('This invite link is not valid; you can still sign up.')}</p>}
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('First name')}><input value={form.first_name} onChange={set('first_name')} className={inputCls} autoComplete="given-name" /></Field>
          <Field label={t('Last name')}><input value={form.last_name} onChange={set('last_name')} className={inputCls} autoComplete="family-name" /></Field>
        </div>
        <Field label={t('Email')}><input type="email" required value={form.email} onChange={set('email')} className={inputCls} autoComplete="email" /></Field>
        <PasswordInput value={form.password} onChange={(v) => setForm((f) => ({ ...f, password: v }))} autoComplete="new-password" />
        <ul className="space-y-0.5 text-[11px]">
          {CHECKS.map(([label, ok]) => (
            <li key={label} className={ok(form.password) ? 'text-emerald-400' : 'text-slate-500'}>{ok(form.password) ? '✓' : '•'} {t(label)}</li>
          ))}
        </ul>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('Country (2 letters)')}><input value={form.country} maxLength={2} onChange={set('country')} className={cx(inputCls, 'uppercase')} placeholder="IN" /></Field>
          <Field label={t('Telegram')}><input value={form.telegram} onChange={set('telegram')} className={inputCls} placeholder="@name" /></Field>
        </div>
        <Field label={t('Website / channel')}><input value={form.website} onChange={set('website')} className={inputCls} placeholder="https://" /></Field>
        <Field label={t('Where will your traffic come from?')}>
          <textarea value={form.traffic_description} onChange={set('traffic_description')} rows={2} className={cx(inputCls, 'py-2')} />
        </Field>
        <label className="flex items-start gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} className="mt-0.5 h-4 w-4" required />
          {t('I am 18+ and I will not target minors. I will use responsible-gambling wording in my promotions.')}
        </label>
        {terms && (
          <label className="flex items-start gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} className="mt-0.5 h-4 w-4" required />
            <span>{t('I accept the')} <a href="/partner/terms" target="_blank" className="text-blue-300 underline">{t('partner terms')}</a> (v{terms.version}).</span>
          </label>
        )}
        {error && <p className="rounded-xl bg-rose-500/10 p-3 text-xs text-rose-300" role="alert">{error}</p>}
        <Btn type="submit" busy={busy} className="w-full" disabled={!CHECKS.every(([, ok]) => ok(form.password))}>{t('Create partner account')}</Btn>
      </form>
      <p className="text-center text-xs text-slate-400">{t('Already a partner?')} <Link to="/partner/login" className="font-bold text-blue-300">{t('Sign in')}</Link></p>
    </Shell>
  )
}

export const PartnerVerifyEmail: React.FC = () => {
  const t = useT()
  const [params] = useSearchParams()
  const token = params.get('token')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const state = token ? result : { ok: false, text: 'The link is incomplete.' }
  useEffect(() => {
    if (!token) return
    partnerApi.verifyEmail(token)
      .then((r) => setResult({ ok: true, text: r.status === 'PENDING' ? 'Email confirmed. Our team will review your application shortly.' : 'Email confirmed. You can sign in now.' }))
      .catch((e) => setResult({ ok: false, text: errorText(e, 'This link is invalid or has expired') }))
  }, [token])
  return (
    <Shell title={state === null ? t('Confirming…') : state.ok ? t('Email confirmed') : t('Link not valid')}>
      <p className="text-center text-sm text-slate-300">{state ? t(state.text) : t('Please wait.')}</p>
      <Link to="/partner/login" className="block text-center text-sm font-bold text-blue-300 underline">{t('Go to sign in')}</Link>
    </Shell>
  )
}

export const PartnerTerms: React.FC = () => {
  const t = useT()
  const [text, setText] = useState<string | null>(null)
  useEffect(() => { partnerApi.terms().then((r) => setText(r.terms?.content || 'No terms published yet.')).catch(() => setText('Could not load the terms.')) }, [])
  return (
    <Shell title={t('Partner terms')}>
      <div className="max-h-[60dvh] overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{text === null ? t('loading') : t(text)}</div>
    </Shell>
  )
}

/** Opened by support/admin in a new tab: /partner/impersonate#token=... (read-only partner view). */
export const PartnerImpersonate: React.FC = () => {
  const t = useT()
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  // Read once: the effect below strips the token from the address bar
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || impersonation.get())
  const [failure, setFailure] = useState<string | null>(null)
  const error = token ? failure : 'Missing token'
  useEffect(() => {
    if (!token) return
    impersonation.set(token)
    window.history.replaceState(null, '', '/partner/impersonate')
    setAccessToken(token)
    authApi.getCurrentUser()
      .then((user) => { setAuth(user, token); navigate('/partner/dashboard', { replace: true }) })
      .catch((e) => setFailure(errorText(e, 'The view has expired')))
  }, [token, navigate, setAccessToken, setAuth])
  return <Shell title={t('Opening partner view…')}>{error && <p className="text-center text-sm text-rose-300">{t(error)}</p>}</Shell>
}
