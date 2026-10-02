import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Clock3, RefreshCw, Volume2, Wallet, Gift, Ticket, X } from 'lucide-react'
import { WinGoBall } from './WinGoBall'
import { WinGoBetSheet, QUANTITY_MULTIPLIERS } from './WinGoBetSheet'
import { WinGoResultPopup, type SettledBet } from './WinGoResultPopup'
import { WinGoHistoryTabs } from './WinGoHistoryTabs'
import { useWingoRound } from './useWingoRound'
import { DEFAULT_PAYOUTS_X100, WINGO_MODES, payoutX100, pickLabel, type WingoPick } from './wingoRules'
import type { WingoResult } from './useWingoRound'
import { apiClient } from '../../../services/api'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'
import { syncWalletBalance } from '../../../services/wallet.api'
import { useWalletStore } from '../../../store/wallet.store'
import { useAuthStore } from '../../../store/auth.store'
import { showToast } from '../../../components/common/Toast'
import { BrandLogo } from '../../../components/common/BrandLogo'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'

interface MyBet { id: number; roundId: string; period: string; gameId: string; pick: WingoPick; amountPaise: number }
interface GameLimits { min_bet: number; max_bet: number }

const pad2 = (n: number) => String(n).padStart(2, '0')

/** Best-case multiplier (x100) for a pick, used for the "max win" preview. */
const maxPayoutX100 = (pick: WingoPick) =>
  pick.type === 'NUMBER' ? DEFAULT_PAYOUTS_X100.NUMBER
    : pick.type === 'SIZE' ? DEFAULT_PAYOUTS_X100.SIZE
      : pick.value === 'VIOLET' ? DEFAULT_PAYOUTS_X100.VIOLET : DEFAULT_PAYOUTS_X100[pick.value]

const chipClass = (pick: WingoPick) =>
  pick.type === 'SIZE' ? (pick.value === 'BIG' ? 'bg-amber-400' : 'bg-sky-500')
    : pick.type === 'NUMBER' ? 'bg-slate-700'
      : pick.value === 'GREEN' ? 'bg-emerald-500' : pick.value === 'RED' ? 'bg-rose-500' : 'bg-violet-500'

function useBallSize() {
  const compute = () => (typeof window === 'undefined' ? 52 : window.innerWidth < 360 ? 40 : window.innerWidth < 420 ? 46 : 54)
  const [size, setSize] = useState(compute)
  useEffect(() => {
    const onResize = () => setSize(compute())
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return size
}

/** Ball that shuffles numbers while the server draws the result. */
const DrawingBall: React.FC = () => {
  const [n, setN] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setN((v) => (v + 3) % 10), 90)
    return () => clearInterval(timer)
  }, [])
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="animate-bounce"><WinGoBall number={n} size={84} /></div>
      <p className="rounded-full bg-white/90 px-4 py-1 text-sm font-black text-rose-500 shadow">Drawing result…</p>
    </div>
  )
}

let betSeq = 0

export const WinGo: React.FC = () => {
  const [modeIndex, setModeIndex] = useState(0)
  const mode = WINGO_MODES[modeIndex]
  const round = useWingoRound(mode.gameId)
  const { isAuthenticated } = useAuthStore()
  const balance = useWalletStore((s) => s.balance.realBalancePaise)
  const ballSize = useBallSize()
  const [limits, setLimits] = useState({ min: 1, max: 10000 })
  const [pick, setPick] = useState<WingoPick | null>(null)
  const [multiplier, setMultiplier] = useState(1)
  const [busy, setBusy] = useState(false)
  const [showRules, setShowRules] = useState(false)
  const [popup, setPopup] = useState<{ result: WingoResult; bets: SettledBet[] } | null>(null)
  const [recent, setRecent] = useState<number[]>([])
  const [myHistoryKey, setMyHistoryKey] = useState(0)
  const [pending, setPending] = useState<MyBet[]>([])
  const pendingRef = useRef<MyBet[]>([])
  useEffect(() => { pendingRef.current = pending }, [pending])
  const [key, rotateKey] = useIdempotencyKey()

  useEffect(() => {
    apiClient.get<GameLimits>(`/games/${mode.gameId}`)
      .then(({ data }) => setLimits({ min: data.min_bet / 100, max: data.max_bet / 100 }))
      .catch(() => undefined)
  }, [mode.gameId])

  useEffect(() => { if (isAuthenticated) void syncWalletBalance().catch(() => undefined) }, [isAuthenticated])

  // Result arrived: settle our bets for that period and show the centre result card
  useEffect(() => {
    const result = round.lastResult
    if (!result) return
    const settled: SettledBet[] = pendingRef.current
      .filter((b) => b.roundId === result.roundId)
      .map((b) => ({ pick: b.pick, amountPaise: b.amountPaise, winPaise: Math.floor((b.amountPaise * payoutX100(b.pick, result.number, result.payoutsX100)) / 100) }))
    pendingRef.current = pendingRef.current.filter((b) => b.roundId !== result.roundId)
    setPending(pendingRef.current)
    if (settled.length) setPopup({ result, bets: settled })
    setTimeout(() => {
      void syncWalletBalance().catch(() => undefined)
      setMyHistoryKey((k) => k + 1)
    }, 1500)
  }, [round.lastResult])

  const choose = (next: WingoPick) => {
    if (!isAuthenticated) {
      showToast({ title: 'Sign in to play', message: 'Create an account or sign in to place bets.', type: 'info' })
      return
    }
    if (round.locked || !round.roundId) return
    setPick(next)
  }

  const closeSheet = useCallback(() => setPick(null), [])
  const closePopup = useCallback(() => setPopup(null), [])

  const confirm = async (totalRupees: number) => {
    if (!pick || !round.roundId || busy) return
    setBusy(true)
    try {
      await apiClient.post('/games/wingo/action', {
        game_id: mode.gameId,
        round_id: round.roundId,
        amount: rupeeToPaise(totalRupees),
        bet_type: pick.type,
        value: pick.value,
      }, { headers: { 'Idempotency-Key': key } })
      betSeq += 1
      pendingRef.current = [...pendingRef.current, { id: betSeq, roundId: round.roundId as string, period: round.period, gameId: mode.gameId, pick, amountPaise: rupeeToPaise(totalRupees) }]
      setPending(pendingRef.current)
      void syncWalletBalance().catch(() => undefined)
      setMyHistoryKey((k) => k + 1)
      showToast({ title: 'Bet placed', message: `₹${totalRupees} on ${pick.type === 'NUMBER' ? `number ${pick.value}` : pickLabel(pick)} • ${round.period}`, type: 'success', duration: 2500 })
      setPick(null)
    } catch (error) {
      showToast({ title: 'Bet rejected', message: getApiErrorMessage(error, 'Betting may be closed for this period.'), type: 'error' })
    } finally {
      rotateKey()
      setBusy(false)
    }
  }

  const minutes = Math.floor(round.secondsLeft / 60)
  const seconds = round.secondsLeft % 60
  const digits = [...pad2(minutes), ':', ...pad2(seconds)]
  const finalCountdown = round.roundId !== null && round.locked && round.secondsLeft > 0 && round.secondsLeft <= 5
  const drawing = round.roundId !== null && round.locked && round.secondsLeft === 0 && round.lastResult?.roundId !== round.roundId
  const canBet = isAuthenticated && !round.locked && round.roundId !== null
  const slip = pending.filter((b) => b.gameId === mode.gameId)
  const slipTotal = slip.reduce((s, b) => s + b.amountPaise, 0)
  const slipMaxWin = slip.reduce((s, b) => s + Math.floor((b.amountPaise * maxPayoutX100(b.pick)) / 100), 0)

  return (
    <div className="mx-auto w-full max-w-xl lg:max-w-6xl">
      <div className="lg:grid lg:grid-cols-[minmax(0,540px)_minmax(0,1fr)] lg:items-start lg:gap-6">
        {/* ---------------- Game column ---------------- */}
        <div className="-mx-4 overflow-hidden bg-[#f6f7fb] pb-5 shadow-2xl sm:mx-0 sm:rounded-3xl">
          <div className="relative bg-gradient-to-b from-rose-500 to-orange-400 px-4 pb-20 pt-4">
            <div className="flex items-center justify-center gap-2 text-white">
              <BrandLogo iconClassName="h-9 w-9 rounded-xl bg-white/20 text-white" textClassName="text-xl font-black tracking-wide" />
              <span className="ml-1 rounded-md bg-white/20 px-2 py-0.5 text-xs font-bold">WinGo</span>
            </div>
          </div>
          <div className="relative -mt-16 px-3 sm:px-4">
            <div className="rounded-3xl bg-white p-4 text-center shadow-lg">
              <div className="flex items-center justify-center gap-2">
                <span className="text-2xl font-black text-slate-800">{formatPaiseToRupee(balance)}</span>
                <button type="button" aria-label="Refresh balance" onClick={() => void syncWalletBalance().catch(() => undefined)} className="text-slate-400 hover:text-slate-600"><RefreshCw className="h-4 w-4" /></button>
              </div>
              <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-slate-500"><Wallet className="h-4 w-4 text-rose-500" />Wallet balance</p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Link to="/wallet" className="rounded-full bg-rose-500 py-2.5 text-sm font-bold text-white shadow">Wallet</Link>
                <Link to="/wallet" className="flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 py-2.5 text-sm font-bold text-white shadow"><Gift className="h-4 w-4" />Daily bonus</Link>
              </div>
            </div>
          </div>

          <div className="space-y-3 px-3 pt-3 sm:px-4">
            <div className="flex items-center gap-2 overflow-hidden rounded-full bg-white px-3 py-2 shadow-sm">
              <Volume2 className="h-4 w-4 shrink-0 text-rose-500" />
              <div className="relative flex-1 overflow-hidden whitespace-nowrap text-xs text-slate-600">
                <span className="inline-block animate-[marquee_18s_linear_infinite]">Virtual credits only — play for fun, never share your password, and take breaks with Responsible Play.</span>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-1 rounded-2xl bg-white p-1 shadow-sm">
              {WINGO_MODES.map((m, index) => (
                <button key={m.gameId} type="button" onClick={() => { setModeIndex(index); setPick(null) }} className={`flex flex-col items-center gap-1 rounded-xl py-2 text-[11px] transition sm:text-xs ${index === modeIndex ? 'bg-gradient-to-b from-rose-400 to-rose-500 text-white shadow' : 'text-slate-400'}`}>
                  <Clock3 className="h-6 w-6 sm:h-7 sm:w-7" />
                  <span className="text-center leading-tight">WinGo<br />{m.short}</span>
                </button>
              ))}
            </div>

            <div className="grid grid-cols-[1fr_auto] gap-3 rounded-2xl bg-gradient-to-r from-rose-500 to-orange-400 p-3 text-white shadow">
              <div className="min-w-0 space-y-2 border-r border-dashed border-white/50 pr-3">
                <button type="button" onClick={() => setShowRules(true)} className="flex items-center gap-1.5 rounded-full border border-white/70 px-3 py-1 text-xs"><BookOpen className="h-3.5 w-3.5" />How to play</button>
                <p className="text-sm">{mode.label}</p>
                <div className="flex gap-1 overflow-hidden">{recent.map((n, i) => <WinGoBall key={i} number={n} size={24} />)}</div>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold">Time remaining</p>
                <div className="mt-1 flex justify-end gap-1">
                  {digits.map((d, i) => (d === ':'
                    ? <span key={i} className="flex w-2.5 items-center justify-center text-xl font-black">:</span>
                    : <span key={i} className="flex h-9 w-6 items-center justify-center rounded bg-white text-xl font-black text-slate-800 sm:w-7">{d}</span>))}
                </div>
                <p className="mt-2 font-mono text-xs font-bold sm:text-sm">{round.period || '—'}</p>
              </div>
            </div>

            {/* Betting board */}
            <div className="relative space-y-3 rounded-2xl bg-white p-3 shadow-sm">
              {!round.connected && <p className="text-center text-xs text-slate-400">Connecting to the game server…</p>}
              <div className="grid grid-cols-3 gap-2">
                {(['GREEN', 'VIOLET', 'RED'] as const).map((c) => (
                  <button
                    key={c}
                    type="button"
                    disabled={!canBet}
                    onClick={() => choose({ type: 'COLOR', value: c })}
                    className={`py-3 text-sm font-bold text-white shadow transition active:scale-95 disabled:opacity-60 ${c === 'GREEN' ? 'rounded-xl rounded-tr-3xl rounded-bl-3xl bg-emerald-500' : c === 'VIOLET' ? 'rounded-xl bg-violet-500' : 'rounded-xl rounded-tl-3xl rounded-br-3xl bg-rose-500'}`}
                  >
                    {c.charAt(0) + c.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-5 justify-items-center gap-2 rounded-2xl bg-slate-50 p-2 sm:p-3">
                {Array.from({ length: 10 }, (_, n) => (
                  <WinGoBall key={n} number={n} size={ballSize} disabled={!canBet} onClick={() => choose({ type: 'NUMBER', value: String(n) })} />
                ))}
              </div>

              <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
                <button type="button" disabled={!canBet} onClick={() => choose({ type: 'NUMBER', value: String(Math.floor(Math.random() * 10)) })} className="shrink-0 rounded-lg border border-rose-500 px-3 py-1.5 text-xs font-bold text-rose-500 disabled:opacity-50">Random</button>
                {QUANTITY_MULTIPLIERS.map((m) => (
                  <button key={m} type="button" onClick={() => setMultiplier(m)} className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold ${multiplier === m ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-500'}`}>X{m}</button>
                ))}
              </div>

              <div className="grid grid-cols-2 overflow-hidden rounded-full">
                <button type="button" disabled={!canBet} onClick={() => choose({ type: 'SIZE', value: 'BIG' })} className="bg-amber-400 py-3 text-sm font-black text-white disabled:opacity-60">Big</button>
                <button type="button" disabled={!canBet} onClick={() => choose({ type: 'SIZE', value: 'SMALL' })} className="bg-sky-500 py-3 text-sm font-black text-white disabled:opacity-60">Small</button>
              </div>

              {finalCountdown && (
                <div className="absolute inset-0 z-10 flex items-center justify-center gap-3 rounded-2xl bg-black/40 backdrop-blur-[1px] sm:gap-4">
                  {pad2(seconds).split('').map((d, i) => (
                    <span key={i} className="flex h-28 w-20 items-center justify-center rounded-2xl bg-white/95 text-7xl font-black text-rose-500 shadow-2xl sm:h-36 sm:w-24 sm:text-8xl">{d}</span>
                  ))}
                </div>
              )}
              {drawing && (
                <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-black/35 backdrop-blur-[1px]">
                  <DrawingBall />
                </div>
              )}
              {!isAuthenticated && (
                <p className="text-center text-xs text-slate-500"><Link to="/login" className="font-bold text-rose-500">Sign in</Link> to place bets.</p>
              )}
            </div>

            {/* Bet slip for the running period */}
            {slip.length > 0 && (
              <div className="rounded-2xl bg-white p-3 shadow-sm">
                <div className="mb-2 flex items-center justify-between">
                  <p className="flex items-center gap-1.5 text-sm font-black text-slate-800"><Ticket className="h-4 w-4 text-rose-500" />My bets • {slip[0].period}</p>
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700">Waiting for result</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {slip.map((b) => (
                    <span key={b.id} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold text-white ${chipClass(b.pick)}`}>
                      {b.pick.type === 'NUMBER' ? `#${b.pick.value}` : pickLabel(b.pick)} · {formatPaiseToRupee(b.amountPaise)}
                    </span>
                  ))}
                </div>
                <div className="mt-2 flex justify-between border-t border-slate-100 pt-2 text-xs text-slate-500">
                  <span>Total stake <b className="text-slate-800">{formatPaiseToRupee(slipTotal)}</b></span>
                  <span>Max win <b className="text-emerald-600">{formatPaiseToRupee(slipMaxWin)}</b></span>
                </div>
              </div>
            )}

            <div className="lg:hidden">
              <WinGoHistoryTabs gameId={mode.gameId} latest={round.lastResult} myHistoryKey={myHistoryKey} onRecent={setRecent} />
            </div>
          </div>
        </div>

        {/* ---------------- History column (desktop) ---------------- */}
        <div className="hidden lg:sticky lg:top-4 lg:block">
          <WinGoHistoryTabs gameId={mode.gameId} latest={round.lastResult} myHistoryKey={myHistoryKey} onRecent={setRecent} />
        </div>
      </div>

      <WinGoBetSheet
        open={pick !== null}
        pick={pick}
        modeLabel={mode.label}
        multiplier={multiplier}
        onMultiplier={setMultiplier}
        locked={round.locked}
        busy={busy}
        minRupees={limits.min}
        maxRupees={limits.max}
        onClose={closeSheet}
        onConfirm={(total) => void confirm(total)}
      />
      <WinGoResultPopup result={popup?.result ?? null} bets={popup?.bets ?? []} modeLabel={mode.label} onClose={closePopup} />

      {showRules && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4" onClick={() => setShowRules(false)}>
          <div className="relative max-h-[85vh] w-full max-w-sm overflow-y-auto rounded-3xl bg-white p-5 text-sm text-slate-600" onClick={(e) => e.stopPropagation()}>
            <button type="button" aria-label="Close" onClick={() => setShowRules(false)} className="absolute right-4 top-4 text-slate-400"><X className="h-5 w-5" /></button>
            <h3 className="mb-3 text-center text-lg font-black text-rose-500">How to play</h3>
            <p>Every {mode.label} period draws one number from 0 to 9. Betting closes 5 seconds before the draw.</p>
            <ul className="mt-3 list-disc space-y-1 pl-5">
              <li><b className="text-emerald-600">Green</b>: 1, 3, 7, 9 pay 2x · 5 pays 1.5x</li>
              <li><b className="text-rose-600">Red</b>: 2, 4, 6, 8 pay 2x · 0 pays 1.5x</li>
              <li><b className="text-violet-600">Violet</b>: 0 or 5 pays 4.5x</li>
              <li><b>Number</b>: exact number pays 9x</li>
              <li><b className="text-amber-500">Big</b> (5-9) / <b className="text-sky-600">Small</b> (0-4): 1.96x</li>
            </ul>
            <p className="mt-3">Your total bet = amount × quantity. You can place several bets in one period. Results are provably fair: the server seed hash is published before betting and revealed after the draw.</p>
            <button type="button" onClick={() => setShowRules(false)} className="mt-4 w-full rounded-full bg-gradient-to-r from-rose-500 to-orange-400 py-2.5 font-bold text-white">Got it</button>
          </div>
        </div>
      )}
    </div>
  )
}
