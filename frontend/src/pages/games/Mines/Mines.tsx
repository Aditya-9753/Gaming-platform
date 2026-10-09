import React, { useEffect, useMemo, useRef, useState } from 'react'
import { MinesBoard, type CellState } from './MinesBoard'
import { MinesControls } from './MinesControls'
import { SkullBomb } from './MinesArt'
import { MyBetsHistory } from '../../../components/games/MyBetsHistory'
import { ProvablyFairBadge } from '../../../components/games/ProvablyFairBadge'
import { showToast } from '../../../components/common/Toast'
import { rupeeToPaise, formatPaiseToRupee } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { syncWalletBalance } from '../../../services/wallet.api'
import { getApiErrorMessage } from '../../../utils/apiError'
import { playSound, playWinFor } from '../../../utils/sounds'
import { t as tr } from '../../../i18n'

interface MinesSession {
  round_id: string
  entry_id: string
  bet_amount: number
  mine_count: number
  revealed_tiles: number[]
  current_multiplier: number
  next_multiplier?: number | null
  current_payout: number
  status: 'IN_PROGRESS' | 'WON' | 'LOST' | string
  mines: number[] | null
  server_seed_hash: string
  server_seed: string | null
}

export const Mines: React.FC = () => {
  const [mineCount, setMineCount] = useState(3)
  const [betRupees, setBetRupees] = useState('10')
  const [session, setSession] = useState<MinesSession | null>(null)
  const [busy, setBusy] = useState(false)
  const [pendingTiles, setPendingTiles] = useState<number[]>([])
  const [historyKey, setHistoryKey] = useState(0)
  const busyRef = useRef(false)
  // Taps made while a reveal is in flight wait here and are sent one by one
  const queueRef = useRef<number[]>([])
  const drainingRef = useRef(false)

  const isPlaying = session?.status === 'IN_PROGRESS'

  // Resume an unfinished game after a reload / navigation.
  useEffect(() => {
    apiClient.get<MinesSession | null>('/games/mines/active')
      .then(({ data }) => { if (data) setSession(data) })
      .catch(() => undefined)
  }, [])
  const grid = useMemo<CellState[]>(() => {
    const revealed = new Set(session?.revealed_tiles ?? [])
    const mines = new Set(session?.mines ?? [])
    return Array.from({ length: 25 }, (_, index) => ({
      revealed: revealed.has(index) || mines.has(index),
      isMine: mines.has(index),
      isHit: mines.has(index) && revealed.has(index),
      ghost: !revealed.has(index) && mines.size > 0,
    }))
  }, [session])

  const sendAction = async (body: Record<string, unknown>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      // A fresh key per move: two quick moves must never share one (the server would treat the second as a replay)
      const { data } = await apiClient.post<MinesSession>('/games/mines/action', body, {
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
      setSession(data)
      if (data.status !== 'IN_PROGRESS') setHistoryKey((k) => k + 1)
      if (body.action === 'start' || data.status !== 'IN_PROGRESS') {
        void syncWalletBalance().catch(() => showToast({ title: tr('Wallet refresh delayed'), message: tr('The game action completed; refresh your wallet to see the latest balance.'), type: 'warning' }))
      }
      return data
    } catch (error) {
      showToast({ title: tr('Action failed'), message: getApiErrorMessage(error, 'The server could not process that move. Please retry.'), type: 'error' })
      return undefined
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const handleStart = async () => {
    const amount = Number(betRupees)
    if (!Number.isFinite(amount) || amount <= 0) {
      showToast({ title: tr('Invalid bet'), message: tr('Enter a valid bet amount.'), type: 'error' })
      return
    }
    const result = await sendAction({
      action: 'start',
      bet_amount: rupeeToPaise(amount),
      mine_count: mineCount,
    })
    if (result) playSound('bet')
    if (result) showToast({ title: tr('Game started'), message: tr('{count} mines hidden. Reveal gems and cash out before you hit one!', { count: mineCount }), type: 'info' })
  }

  const drainQueue = async () => {
    if (drainingRef.current) return
    drainingRef.current = true
    try {
      while (queueRef.current.length) {
        const index = queueRef.current[0]
        const result = await sendAction({ action: 'reveal', tile_index: index })
        queueRef.current.shift()
        if (result?.status === 'LOST') { playSound('bomb'); window.setTimeout(() => playSound('lose'), 450) }
        else if (result) playSound('gem')
        if (!result || result.status !== 'IN_PROGRESS') {
          queueRef.current = [] // mine hit, round over or error: drop the remaining taps
          if (result?.status === 'LOST') {
            showToast({ title: tr('Boom! Mine hit'), message: tr('You lost {amount}. The mine layout is now revealed.', { amount: formatPaiseToRupee(result.bet_amount) }), type: 'error' })
          }
        }
        setPendingTiles([...queueRef.current])
      }
    } finally {
      drainingRef.current = false
    }
  }

  const handleCellClick = (index: number) => {
    if (!isPlaying || session?.revealed_tiles.includes(index) || queueRef.current.includes(index)) return
    queueRef.current.push(index)
    setPendingTiles([...queueRef.current])
    void drainQueue()
  }

  const handleCashout = async () => {
    const result = await sendAction({ action: 'cashout' })
    if (result?.status === 'WON') {
      playSound('cashout')
      window.setTimeout(() => playWinFor(result.current_payout, result.bet_amount), 150)
      showToast({
        title: tr('Cashed out!'),
        message: `You won ${formatPaiseToRupee(result.current_payout)} at ${result.current_multiplier.toFixed(2)}x.`,
        type: 'success',
      })
    }
  }

  const potentialWinPaise = session?.current_payout ?? 0

  const ended = session !== null && session.status !== 'IN_PROGRESS'

  return (
    <div className="-mx-2 sm:mx-auto max-w-5xl overflow-hidden rounded-2xl sm:rounded-3xl bg-[radial-gradient(ellipse_at_top,#ff8a3d_0%,#d6261f_38%,#5a0b16_75%,#1c0610_100%)] p-3 sm:p-6 shadow-2xl">
      <div className="mb-3 sm:mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 sm:gap-3">
          <SkullBomb className="h-10 w-10 sm:h-14 sm:w-14 drop-shadow-[0_0_12px_rgba(251,146,60,0.9)]" />
          <div>
            <h2 className="bg-gradient-to-b from-[#fff6c9] via-[#fbbf24] to-[#b45309] bg-clip-text font-black italic tracking-wide text-transparent drop-shadow-[0_3px_0_rgba(80,10,40,0.9)] text-2xl sm:text-4xl">{tr('MINES')}</h2>
            <span className="text-[11px] sm:text-xs font-semibold text-amber-100/80">{tr('Find the gems • dodge the bombs')}</span>
          </div>
        </div>
        <ProvablyFairBadge className="hidden sm:inline-flex" />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-3">
          <MinesBoard grid={grid} onCellClick={handleCellClick} disabled={!isPlaying} pendingTiles={pendingTiles} />
          {ended && (
            <div className={`rounded-2xl px-4 py-3 text-center font-black ${session.status === 'WON' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-black/40 text-rose-300'}`}>
              {session.status === 'WON'
                ? `You won ${formatPaiseToRupee(session.current_payout)} at ${session.current_multiplier.toFixed(2)}x!`
                : `Boom! Lost ${formatPaiseToRupee(session.bet_amount)} — play again?`}
            </div>
          )}
          {session && (
            <details className="rounded-xl bg-black/30 px-3 py-2 text-[11px] text-amber-100/70">
              <summary className="cursor-pointer font-semibold">{tr('Provably fair details')}</summary>
              <p className="mt-1 break-all">{tr('Commitment:')} <span className="font-mono">{session.server_seed_hash}</span></p>
              {ended && session.server_seed && <p className="mt-1 break-all">{tr('Server seed:')} <span className="font-mono">{session.server_seed}</span></p>}
            </details>
          )}
        </div>
        <MinesControls
          betRupees={betRupees}
          setBetRupees={setBetRupees}
          mineCount={mineCount}
          setMineCount={setMineCount}
          isPlaying={Boolean(isPlaying)}
          onStart={handleStart}
          onCashout={handleCashout}
          currentMultiplier={session?.current_multiplier ?? 1}
          nextMultiplier={session?.next_multiplier ?? null}
          canCashout={Boolean(session && session.revealed_tiles.length > 0)}
          busy={busy}
          potentialWinPaise={potentialWinPaise}
          gemsFound={isPlaying ? session?.revealed_tiles.length ?? 0 : 0}
        />
      </div>

      <section className="mt-4 sm:mt-5 rounded-2xl bg-black/40 p-3 sm:p-4">
        <MyBetsHistory gameId="mines" refreshKey={historyKey} title={tr('My Mines history')} />
      </section>
    </div>
  )
}
