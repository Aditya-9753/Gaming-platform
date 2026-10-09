import React, { Suspense, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3, BookOpen, Eye, HelpCircle, LayoutDashboard, LogOut, Mail, Megaphone, Menu, MessageCircle, Network,
  Smartphone, Star, User, Wallet, X,
} from 'lucide-react'
import { BrandLogo } from '../../components/common/BrandLogo'
import { Loader } from '../../components/common/Loader'
import { ToastContainer } from '../../components/common/Toast'
import { ErrorBoundary } from '../../components/common/ErrorBoundary'
import { Badge, Btn, Money, cx, errorText, pct } from '../../components/affiliate/ui'
import { authApi } from '../../services/auth.api'
import { partnerApi } from '../../services/affiliate.api'
import { useAuthStore } from '../../store/auth.store'
import { usePartnerStore } from './partner.store'
import { impersonation } from '../../utils/impersonation'
import { LANGUAGE_NAMES, useT, type TKey } from './i18n'

const TILES: Array<{ to: string; key: TKey; icon: React.ReactNode; sub?: boolean }> = [
  { to: '/partner/dashboard', key: 'dashboard', icon: <LayoutDashboard className="h-5 w-5" /> },
  { to: '/partner/pr-tools', key: 'prTools', icon: <Megaphone className="h-5 w-5" /> },
  { to: '/partner/sources', key: 'sources', icon: <Network className="h-5 w-5" /> },
  { to: '/partner/statistics', key: 'statistics', icon: <BarChart3 className="h-5 w-5" /> },
  { to: '/partner/withdrawal', key: 'withdrawal', icon: <Wallet className="h-5 w-5" /> },
  { to: '/partner/subpartners', key: 'subpartners', icon: <User className="h-5 w-5" />, sub: true },
  { to: '/partner/faq', key: 'faq', icon: <HelpCircle className="h-5 w-5" /> },
  { to: '/partner/contacts', key: 'contacts', icon: <MessageCircle className="h-5 w-5" /> },
  { to: '/partner/blog', key: 'blog', icon: <BookOpen className="h-5 w-5" /> },
]

const dealLabel = (type?: string | null, rate?: string | null, t?: (k: TKey) => string) => {
  if (!type) return '—'
  const name = t ? t(type.toLowerCase() as TKey) || type : type
  return rate && Number(rate) > 0 && type !== 'CPA' ? `${name}: ${pct(rate)}` : name
}

/** Pages a partner may open before approval / verification. */
const OPEN_WHILE_PENDING = ['/partner/faq', '/partner/contacts', '/partner/profile', '/partner/notifications']

export const PartnerLayout: React.FC = () => {
  const { me, load, error, locale, setLocale } = usePartnerStore()
  const { isAuthenticated, isLoading, user, logout } = useAuthStore()
  const t = useT()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [dealOpen, setDealOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (isAuthenticated && user?.role === 'partner') void load()
  }, [isAuthenticated, user?.role, load, pathname])
  useEffect(() => { setMenuOpen(false) }, [pathname])
  useEffect(() => {
    if (me?.partner.locale && me.partner.locale !== locale && !localStorage.getItem('locale')) setLocale(me.partner.locale)
  }, [me?.partner.locale, locale, setLocale])

  if (isLoading) return <Loader fullScreen />
  if (!isAuthenticated) return <Navigate to="/partner/login" replace />
  if (user?.role !== 'partner') return <Navigate to={user?.role === 'user' ? '/dashboard' : '/admin/dashboard'} replace />
  if (!me) {
    return error ? (
      <div className="flex min-h-[100dvh] items-center justify-center bg-dark-bg p-6 text-center text-sm text-slate-300">
        <div className="space-y-3"><p>{error}</p><Btn onClick={() => void load()}>{t('retry')}</Btn></div>
      </div>
    ) : <Loader fullScreen />
  }

  const exit = async () => {
    setBusy(true)
    try {
      if (!me.impersonated_by) await authApi.logout()
    } catch { /* already signed out */ }
    impersonation.clear()
    usePartnerStore.getState().clear()
    logout()
    setBusy(false)
    navigate(me.impersonated_by ? '/admin/affiliate/partners' : '/partner/login', { replace: true })
  }

  const p = me.partner
  const gated = !OPEN_WHILE_PENDING.some((path) => pathname.startsWith(path))
  const gate = (() => {
    if (me.impersonated_by) return null
    if (!me.email_verified) return <VerifyGate />
    if (p.status === 'PENDING') return <StateCard title={t('pendingApproval')} text="We review every partner application. You will get an email and a notification once your account is approved; your Default tracking link will be ready then." />
    if (p.status === 'SUSPENDED' || p.status === 'BLOCKED') return <StateCard title={t('suspended')} text="Contact your manager through the Contacts page for details." />
    if (me.terms_required) return <TermsGate versionId={me.terms_required.id} version={me.terms_required.version} onDone={() => void load()} />
    return null
  })()
  const tiles = TILES.filter((tile) => !tile.sub || me.subpartners_enabled)

  return (
    <div className="dark flex min-h-[100dvh] flex-col bg-dark-bg text-white">
      {me.impersonated_by && (
        <div className="flex items-center justify-center gap-2 bg-amber-500 px-3 py-1.5 text-center text-xs font-bold text-black">
          <Eye className="h-4 w-4" /> Read-only view of partner {p.partner_code} — changes are disabled
        </div>
      )}
      <header className="sticky top-0 z-40 border-b border-dark-border bg-dark-card/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-2 sm:px-4">
          <Link to="/partner/notifications" className="relative rounded-xl p-2.5 text-slate-300 hover:bg-dark-elevated" aria-label={t('notifications')}>
            <Mail className="h-5 w-5" />
            {me.unread_notifications > 0 && (
              <span className="absolute right-1 top-1 min-w-[16px] rounded-full bg-rose-500 px-1 text-center text-[10px] font-black leading-4">
                {me.unread_notifications > 99 ? '99+' : me.unread_notifications}
              </span>
            )}
          </Link>
          {me.config.app_android_url && (
            <a href={me.config.app_android_url} target="_blank" rel="noreferrer" className="rounded-xl p-2.5 text-emerald-400 hover:bg-dark-elevated" aria-label="Android app">
              <Smartphone className="h-5 w-5" />
            </a>
          )}
          {me.config.app_ios_url && (
            <a href={me.config.app_ios_url} target="_blank" rel="noreferrer" className="rounded-xl p-2.5 text-slate-200 hover:bg-dark-elevated" aria-label="iOS app">
              <Smartphone className="h-5 w-5" />
            </a>
          )}
          <button type="button" onClick={() => setDealOpen((v) => !v)} className="rounded-xl p-2.5 text-amber-400 hover:bg-dark-elevated" aria-label="Your deal">
            <Star className="h-5 w-5" />
          </button>
          <Link to="/partner/dashboard" className="mx-auto min-w-0"><BrandLogo wordmark textClassName="text-base font-black" className="flex items-center" /></Link>
          <button type="button" onClick={() => setMenuOpen(true)} className="rounded-xl p-2.5 text-slate-200 hover:bg-dark-elevated" aria-label="Menu">
            <Menu className="h-6 w-6" />
          </button>
        </div>
        {dealOpen && (
          <div className="mx-auto max-w-5xl px-3 pb-3">
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              <div className="font-black">Your deal: {dealLabel(me.deal?.deal_type, me.deal?.revshare_rate, t)}</div>
              {me.deal && Number(me.deal.cpa_amount) > 0 && <div>CPA {me.deal.cpa_amount} $ per qualified first deposit (min {me.deal.min_ftd_amount} $, hold {me.deal.hold_days} days)</div>}
              <div>Negative balance: {me.deal?.carryover ? 'carried over to the next period' : 'written off at period close'}</div>
            </div>
          </div>
        )}
        <nav className="mx-auto hidden max-w-5xl gap-1 overflow-x-auto px-4 pb-2 lg:flex" aria-label="Partner navigation">
          {tiles.map((tile) => (
            <NavLink key={tile.to} to={tile.to} className={({ isActive }) => cx('flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-bold',
              isActive ? 'bg-brand-blue text-white' : 'text-slate-400 hover:text-white')}>
              {tile.icon}{t(tile.key)}
            </NavLink>
          ))}
        </nav>
      </header>

      {/* Hamburger menu */}
      <div className={cx('fixed inset-0 z-50 bg-black/70 transition-opacity', menuOpen ? 'opacity-100' : 'pointer-events-none opacity-0')} onClick={() => setMenuOpen(false)} aria-hidden="true" />
      <aside className={cx('fixed inset-y-0 right-0 z-50 flex w-[92vw] max-w-sm flex-col bg-dark-card shadow-2xl transition-transform',
        menuOpen ? 'translate-x-0' : 'translate-x-full')} aria-label="Menu">
        <div className="flex items-center gap-3 border-b border-dark-border p-4">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-full bg-brand-blue text-lg font-black">
            {(me.name || '?').slice(0, 1).toUpperCase()}
            <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-dark-card bg-emerald-400" aria-label="online" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate font-black">{me.name}</div>
            <div className="text-[11px] text-slate-400">ID {p.partner_code}</div>
          </div>
          <button type="button" onClick={() => setMenuOpen(false)} className="rounded-lg p-2 text-slate-400 hover:text-white" aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <Link to="/partner/withdrawal" className="block rounded-2xl bg-gradient-to-br from-brand-blue to-indigo-700 p-4 shadow-lg">
            <div className="text-[11px] font-bold uppercase tracking-wide text-blue-100">{t('available')}</div>
            <Money value={me.wallet.available} className={cx('text-2xl font-black', Number(me.wallet.available) < 0 ? 'text-rose-200' : 'text-white')} />
            <div className="mt-1 text-xs font-bold text-blue-100">{dealLabel(me.deal?.deal_type, me.deal?.revshare_rate, t)}</div>
            <div className="mt-2 flex gap-3 text-[11px] text-blue-100/80">
              <span>{t('pending')}: {Number(me.wallet.pending).toFixed(2)} $</span>
              {Number(me.wallet.reserved) > 0 && <span>{t('reserved')}: {Number(me.wallet.reserved).toFixed(2)} $</span>}
            </div>
          </Link>
          <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1">
            {[...tiles, { to: '/partner/profile', key: 'profile' as TKey, icon: <User className="h-5 w-5" /> }].map((tile) => (
              <NavLink key={tile.to} to={tile.to} className={({ isActive }) => cx('flex h-20 w-24 shrink-0 snap-start flex-col items-center justify-center gap-1.5 rounded-2xl border text-center text-[11px] font-bold',
                isActive ? 'border-brand-blue bg-brand-blue/15 text-white' : 'border-dark-border bg-dark-bg text-slate-300')}>
                {tile.icon}<span className="px-1 leading-tight">{t(tile.key)}</span>
              </NavLink>
            ))}
          </div>
          {pathname.startsWith('/partner/statistics') && (
            <div className="flex gap-2 text-xs">
              <Link to="/partner/statistics" className="rounded-lg bg-dark-elevated px-3 py-2 font-bold">{t('common')}</Link>
              {me.subpartners_enabled && <Link to="/partner/statistics?tab=subpartners" className="rounded-lg bg-dark-elevated px-3 py-2 font-bold">{t('subpartners')}</Link>}
            </div>
          )}
        </div>
        <div className="space-y-3 border-t border-dark-border p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">{t('language')}</span>
            <div className="flex gap-1">
              {me.config.languages.map((lang) => (
                <button key={lang} type="button" onClick={() => { setLocale(lang); void partnerApi.updateMe({ locale: lang }).catch(() => undefined) }}
                  className={cx('min-h-[36px] rounded-lg px-3 text-xs font-black', locale === lang ? 'bg-brand-blue text-white' : 'bg-dark-elevated text-slate-300')}>
                  {LANGUAGE_NAMES[lang] || lang.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <Btn tone="ghost" className="w-full" busy={busy} onClick={exit}><LogOut className="h-4 w-4" />{t('exit')}</Btn>
        </div>
      </aside>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-4 sm:py-6">
        <ErrorBoundary>
          <Suspense fallback={<Loader text={t('loading')} />}>
            {gate && gated ? gate : <Outlet />}
          </Suspense>
        </ErrorBoundary>
      </main>
      <ToastContainer />
    </div>
  )
}

const StateCard: React.FC<{ title: string; text: string; children?: React.ReactNode }> = ({ title, text, children }) => (
  <div className="mx-auto mt-6 max-w-md space-y-3 rounded-3xl border border-dark-border bg-dark-card p-6 text-center">
    <h2 className="text-lg font-black">{title}</h2>
    <p className="text-sm text-slate-400">{text}</p>
    {children}
    <p className="text-xs text-slate-500">Questions? <Link to="/partner/contacts" className="text-blue-300 underline">Contact us</Link></p>
  </div>
)

const VerifyGate: React.FC = () => {
  const t = useT()
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  return (
    <StateCard title={t('verifyEmail')} text="We sent you a confirmation link. Open it on this device to activate your account.">
      {err && <p className="text-xs text-rose-300">{err}</p>}
      <Btn tone="ghost" busy={busy} disabled={sent} onClick={async () => {
        setBusy(true)
        try { await partnerApi.resendVerification(); setSent(true) } catch (e) { setErr(errorText(e)) } finally { setBusy(false) }
      }}>{sent ? 'Sent — check your inbox' : 'Send the link again'}</Btn>
    </StateCard>
  )
}

const TermsGate: React.FC<{ versionId: number; version: string; onDone: () => void }> = ({ versionId, version, onDone }) => {
  const [text, setText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { partnerApi.terms().then((r) => setText(r.terms?.content || '')).catch(() => setText('')) }, [])
  return (
    <div className="mx-auto mt-4 max-w-2xl space-y-4 rounded-3xl border border-dark-border bg-dark-card p-5">
      <div className="flex items-center justify-between"><h2 className="text-lg font-black">Partner terms</h2><Badge tone="blue">v{version}</Badge></div>
      <div className="max-h-[50dvh] overflow-y-auto whitespace-pre-wrap rounded-xl bg-dark-bg p-4 text-xs leading-relaxed text-slate-300">{text ?? 'Loading…'}</div>
      <Btn className="w-full" busy={busy} onClick={async () => {
        setBusy(true)
        try { await partnerApi.acceptTerms(versionId); onDone() } finally { setBusy(false) }
      }}>I accept the terms</Btn>
    </div>
  )
}
