import React, { useEffect, useMemo, useRef, useState } from 'react'
import { MinesBoard, type CellState } from './MinesBoard'
import { MinesControls } from './MinesControls'
import { SkullBomb } from './MinesArt'
import { MyBetsHistory } from '../../../components/games/MyBetsHistory'
import { ProvablyFairBadge } from '../../../components/games/ProvablyFairBadge'
import { showToast } from '../../../components/common/Toast'
import { rupeeToPaise, formatPaiseToRupee } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'
import { syncWalletBalance } from '../../../services/wallet.api'
import { getApiErrorMessage } from '../../../utils/apiError'

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
  const [historyKey, setHistoryKey] = useState(0)
  const [key, rotateKey] = useIdempotencyKey()
  const busyRef = useRef(false)

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
      const { data } = await apiClient.post<MinesSession>('/games/mines/action', body, {
        headers: { 'Idempotency-Key': key },
      })
      setSession(data)
      rotateKey()
      if (data.status !== 'IN_PROGRESS') setHistoryKey((k) => k + 1)
      if (body.action === 'start' || data.status !== 'IN_PROGRESS') {
        void syncWalletBalance().catch(() => showToast({ title: 'Wallet refresh delayed', message: 'The game action completed; refresh your wallet to see the latest balance.', type: 'warning' }))
      }
      return data
    } catch (error) {
      rotateKey()
      showToast({ title: 'Action failed', message: getApiErrorMessage(error, 'The server could not process that move. Please retry.'), type: 'error' })
      return undefined
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const handleStart = async () => {
    const amount = Number(betRupees)
    if (!Number.isFinite(amount) || amount <= 0) {
      showToast({ title: 'Invalid bet', message: 'Enter a valid bet amount.', type: 'error' })
      return
    }
    const result = await sendAction({
      action: 'start',
      bet_amount: rupeeToPaise(amount),
      mine_count: mineCount,
    })
    if (result) showToast({ title: 'Game started', message: `${mineCount} mines hidden. Reveal gems and cash out before you hit one!`, type: 'info' })
  }

  const handleCellClick = async (index: number) => {
    if (!isPlaying || session?.revealed_tiles.includes(index)) return
    const result = await sendAction({ action: 'reveal', tile_index: index })
    if (result?.status === 'LOST') {
      showToast({ title: 'Boom! Mine hit', message: `You lost ${formatPaiseToRupee(result.bet_amount)}. The mine layout is now revealed.`, type: 'error' })
    }
  }

  const handleCashout = async () => {
    const result = await sendAction({ action: 'cashout' })
    if (result?.status === 'WON') {
      showToast({
        title: 'Cashed out!',
        message: `You won ${formatPaiseToRupee(result.current_payout)} at ${result.current_multiplier.toFixed(2)}x.`,
        type: 'success',
      })
    }
  }

  const potentialWinPaise = session?.current_payout ?? 0

  const ended = session !== null && session.status !== 'IN_PROGRESS'

  return (
    <div className="mx-auto max-w-5xl overflow-hidden rounded-3xl bg-[radial-gradient(ellipse_at_top,#ff8a3d_0%,#d6261f_38%,#5a0b16_75%,#1c0610_100%)] p-4 sm:p-6 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <SkullBomb className="h-14 w-14 drop-shadow-[0_0_12px_rgba(251,146,60,0.9)]" />
          <div>
            <h2 className="bg-gradient-to-b from-[#fff6c9] via-[#fbbf24] to-[#b45309] bg-clip-text text-4xl font-black italic tracking-wide text-transparent drop-shadow-[0_3px_0_rgba(80,10,40,0.9)]">MINES</h2>
            <span className="text-xs font-semibold text-amber-100/80">Find the gems • dodge the bombs</span>
          </div>
        </div>
        <ProvablyFairBadge />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-3">
          <MinesBoard grid={grid} onCellClick={handleCellClick} disabled={!isPlaying || busy} />
          {ended && (
            <div className={`rounded-2xl px-4 py-3 text-center font-black ${session.status === 'WON' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-black/40 text-rose-300'}`}>
              {session.status === 'WON'
                ? `You won ${formatPaiseToRupee(session.current_payout)} at ${session.current_multiplier.toFixed(2)}x!`
                : `Boom! Lost ${formatPaiseToRupee(session.bet_amount)} — play again?`}
            </div>
          )}
          {session && (
            <details className="rounded-xl bg-black/30 px-3 py-2 text-[11px] text-amber-100/70">
              <summary className="cursor-pointer font-semibold">Provably fair details</summary>
              <p className="mt-1 break-all">Commitment: <span className="font-mono">{session.server_seed_hash}</span></p>
              {ended && session.server_seed && <p className="mt-1 break-all">Server seed: <span className="font-mono">{session.server_seed}</span></p>}
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

      <section className="mt-5 rounded-2xl bg-black/40 p-4">
        <MyBetsHistory gameId="mines" refreshKey={historyKey} title="My Mines history" />
      </section>
    </div>
  )
}
