import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flame, Gift, Radio, Sparkles, Clock } from 'lucide-react'
import { GameTileSection } from './GameTile'
import { DailyClaimCard } from '../wallet/DailyClaimCard'
import { useAuthStore } from '../../store/auth.store'
import { useGames } from '../../hooks/useGames'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'
import { COMING_SOON_SECTIONS, LIVE_GAMES } from '../../utils/lobbyGames'
import { t as tr } from '../../i18n'

interface Slide { kicker: string; title: string; sub: string; art: string; gradient: string; to: string; cta: string }

const SLIDES: Slide[] = [
  { kicker: 'VIP CLUB', title: tr('JOIN & WIN'), sub: 'Daily free bonus for every player', art: '👑', gradient: 'from-slate-700 via-zinc-800 to-black', to: '/register', cta: 'Join now' },
  { kicker: 'NEW • LIVE', title: tr('TEEN PATTI'), sub: 'Player A vs Player B — new hand every 30s', art: '🃏', gradient: 'from-emerald-700 via-green-900 to-black', to: '/games/teen-patti', cta: 'Play now' },
  { kicker: 'CRASH GAME', title: tr('AVIATOR'), sub: 'Fly high, cash out before it flies away', art: '✈️', gradient: 'from-red-700 via-rose-900 to-black', to: '/games/aviator', cta: 'Play now' },
]

const HeroCarousel: React.FC = () => {
  const [index, setIndex] = useState(0)
  const { isAuthenticated } = useAuthStore()
  useEffect(() => {
    const timer = setInterval(() => setIndex((i) => (i + 1) % SLIDES.length), 5000)
    return () => clearInterval(timer)
  }, [])
  const slide = SLIDES[index]
  const to = slide.to === '/register' && isAuthenticated ? '/wallet' : slide.to
  return (
    <section className={`relative h-44 sm:h-60 overflow-hidden rounded-3xl bg-gradient-to-br ${slide.gradient} border border-white/10 shadow-2xl transition-colors duration-700`}>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_40%,rgba(255,255,255,0.18),transparent_55%)]" />
      <span aria-hidden className="absolute right-4 sm:right-12 top-1/2 -translate-y-1/2 text-[88px] sm:text-[150px] leading-none drop-shadow-2xl">{slide.art}</span>
      <div key={index} className="relative z-10 flex h-full flex-col justify-center gap-1 p-5 sm:p-10 animate-[popIn_0.5s_ease-out]">
        <span className="text-[11px] font-black tracking-[0.2em] text-white/70">{slide.kicker}</span>
        <h1 className="text-3xl sm:text-5xl font-black italic uppercase leading-none tracking-tight text-white">{tr(slide.title)}</h1>
        <p className="max-w-[60%] text-xs sm:text-sm text-white/75">{slide.sub}</p>
        <Link to={to} className="mt-2 w-fit rounded-xl bg-brand-blue px-4 py-2 text-xs font-black text-white shadow-lg hover:brightness-110">{slide.cta}</Link>
      </div>
      <div className="absolute bottom-3 left-5 sm:left-10 z-10 flex gap-1.5 rounded-full bg-black/40 px-2 py-1">
        {SLIDES.map((s, i) => (
          <button key={s.title} type="button" aria-label={`Show ${s.title}`} onClick={() => setIndex(i)} className={`h-1.5 rounded-full transition-all ${i === index ? 'w-4 bg-white' : 'w-1.5 bg-white/40'}`} />
        ))}
      </div>
    </section>
  )
}

/** Shared lobby used by Home and the Casino (/games) page. */
export const LobbyHome: React.FC<{ showHero?: boolean }> = ({ showHero = true }) => {
  const { gamesList, fetchGames } = useGames()
  const { isAuthenticated } = useAuthStore()
  const { daily_claim_amount_paise: dailyPaise } = usePlatformConfig()
  useEffect(() => { void fetchGames() }, [fetchGames])

  // Live games switched off by an admin show as "Maintenance"
  const disabled = useMemo(() => new Set(gamesList.filter((g) => !g.isActive).map((g) => g.id as string)), [gamesList])

  return (
    <div className="space-y-6">
      {showHero && (
        <>
          <HeroCarousel />
          <div className="grid grid-cols-[1.7fr_1fr] gap-2.5">
            <Link to={isAuthenticated ? '/wallet' : '/register'} className="relative h-24 sm:h-28 overflow-hidden rounded-2xl bg-gradient-to-r from-amber-700 via-amber-600 to-yellow-500 p-4 shadow-lg">
              <span className="block text-base sm:text-lg font-black leading-tight text-white">{tr('Free')}<br />{tr('bonus')}</span>
              <span className="text-[11px] text-white/85">₹{(dailyPaise / 100).toLocaleString('en-IN')} every day</span>
              <span aria-hidden className="absolute -right-1 bottom-0 text-6xl sm:text-7xl">💰</span>
            </Link>
            <Link to={isAuthenticated ? '/wallet' : '/register'} className="relative h-24 sm:h-28 overflow-hidden rounded-2xl bg-gradient-to-b from-slate-600 to-slate-800 p-3 text-center shadow-lg">
              <span className="block text-sm sm:text-base font-black text-white">{tr('Bonuses')}</span>
              <span aria-hidden className="absolute inset-x-0 bottom-1 text-5xl sm:text-6xl">🎁</span>
            </Link>
          </div>
          {isAuthenticated && <DailyClaimCard />}
        </>
      )}

      <GameTileSection
        title={tr('Live Games')}
        icon={<Flame className="h-5 w-5 text-orange-400" />}
        games={LIVE_GAMES}
        disabledIds={disabled}
        action={<span className="flex items-center gap-1.5 rounded-full bg-green-500/15 px-2.5 py-1 text-[11px] font-black text-green-400"><Radio className="h-3.5 w-3.5" />{tr('LIVE')}</span>}
      />

      {COMING_SOON_SECTIONS.map((section, i) => (
        <GameTileSection
          key={section.id}
          title={tr(section.title)}
          icon={[<Sparkles key="s" className="h-5 w-5 text-purple-300" />, <Gift key="g" className="h-5 w-5 text-rose-300" />, <Clock key="c" className="h-5 w-5 text-amber-300" />, <Radio key="r" className="h-5 w-5 text-sky-300" />][i % 4]}
          games={section.games}
          action={<span className="rounded-full bg-dark-elevated px-2.5 py-1 text-[11px] font-bold text-slate-400">{tr('Coming soon')}</span>}
        />
      ))}
    </div>
  )
}
