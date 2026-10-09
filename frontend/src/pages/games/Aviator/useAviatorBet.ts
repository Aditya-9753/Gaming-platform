import { useCallback, useEffect, useRef, useState } from 'react'
import type { AviatorState } from './useAviatorRound'
import { apiClient } from '../../../services/api'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'
import { syncWalletBalance } from '../../../services/wallet.api'
import { showToast } from '../../../components/common/Toast'
import { playCashout, playSound } from '../../../utils/sounds'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'
import { t as tr } from '../../../i18n'

interface BetResponse { entry_id: string; bet_amount: number }
interface CashoutResponse { multiplier: number; payout_amount: number }

export interface AviatorBetSlot {
  /** Bet accepted for the current/next round. */
  entryId: string | null
  betPaise: number | null
  roundId: string | null
  autoCashout: number | null
  busy: boolean
  place: (amountPaise: number, autoCashout?: number) => Promise<void>
  cashout: () => Promise<void>
}

const refreshWallet = () => { void syncWalletBalance().catch(() => undefined) }

/** One independent Aviator bet (the page renders two, like the original game). */
export function useAviatorBet(round: AviatorState, label: string, onSettled?: () => void): AviatorBetSlot {
  const [entryId, setEntryId] = useState<string | null>(null)
  const [betPaise, setBetPaise] = useState<number | null>(null)
  const [roundId, setRoundId] = useState<string | null>(null)
  const [autoCashout, setAutoCashout] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [key, rotateKey] = useIdempotencyKey()
  const busyRef = useRef(false)

  const clear = useCallback(() => {
    setEntryId(null)
    setBetPaise(null)
    setRoundId(null)
    setAutoCashout(null)
  }, [])

  // Server-side (auto) cashout of this slot's entry
  useEffect(() => {
    const cashout = round.lastCashout
    if (!cashout || !entryId || cashout.entryId !== entryId) return
    playCashout(cashout.multiplier)
    if (cashout.multiplier >= 10) window.setTimeout(() => playSound('bigWin'), 350)
    clear()
    refreshWallet()
    onSettled?.()
    showToast({
      title: cashout.automatic ? tr('{label}: auto cashout!', { label }) : tr('{label}: cashed out!', { label }),
      message: tr('Won {amount} at {x}x.', { amount: formatPaiseToRupee(cashout.payout), x: cashout.multiplier.toFixed(2) }),
      type: 'success',
    })
  }, [round.lastCashout, entryId, clear, label, onSettled])

  // Plane flew away with this bet still riding
  useEffect(() => {
    if (round.phase !== 'crashed' || betPaise === null || roundId !== round.roundId) return
    window.setTimeout(() => playSound('lose'), 700) // after the fly-away whoosh
    showToast({ title: tr('{label}: flew away', { label }), message: tr('Lost {amount} at {x}x.', { amount: formatPaiseToRupee(betPaise), x: round.multiplier.toFixed(2) }), type: 'error' })
    clear()
    refreshWallet()
    onSettled?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [round.phase])

  // A new round began while holding a stale bet (e.g. after reconnecting)
  useEffect(() => {
    if (roundId && round.roundId && roundId !== round.roundId && round.phase === 'betting') clear()
  }, [round.roundId, round.phase, roundId, clear])

  const run = async (fn: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try { await fn() } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const place = (amountPaise: number, auto?: number) => run(async () => {
    if (!round.roundId || entryId) return
    try {
      const { data } = await apiClient.post<BetResponse>('/games/aviator/action', {
        action: 'bet', round_id: round.roundId, amount: amountPaise, auto_cashout: auto,
      }, { headers: { 'Idempotency-Key': key } })
      setEntryId(data.entry_id)
      setBetPaise(data.bet_amount)
      setRoundId(round.roundId)
      setAutoCashout(auto ?? null)
      refreshWallet()
      playSound('bet')
      showToast({ title: tr('{label}: bet placed', { label }), message: tr('{amount} on round #{round}', { amount: formatPaiseToRupee(data.bet_amount), round: round.roundNumber }) + (auto ? ` • ${tr('auto')} ${auto.toFixed(2)}x` : '') + '.', type: 'success' })
    } catch (error) {
      showToast({ title: tr('{label}: bet rejected', { label }), message: getApiErrorMessage(error, tr('The server rejected this bet.')), type: 'error' })
    } finally {
      rotateKey()
    }
  })

  const cashout = () => run(async () => {
    if (!roundId || !entryId) return
    try {
      const { data } = await apiClient.post<CashoutResponse>('/games/aviator/action', {
        action: 'cashout', round_id: roundId, entry_id: entryId,
      }, { headers: { 'Idempotency-Key': key } })
      playCashout(data.multiplier)
      if (data.multiplier >= 10) window.setTimeout(() => playSound('bigWin'), 350)
      clear()
      refreshWallet()
      onSettled?.()
      showToast({ title: tr('{label}: cashed out!', { label }), message: tr('Won {amount} at {x}x.', { amount: formatPaiseToRupee(data.payout_amount), x: data.multiplier.toFixed(2) }), type: 'success' })
    } catch (error) {
      showToast({ title: tr('{label}: cashout failed', { label }), message: getApiErrorMessage(error, tr('The plane may have already flown away.')), type: 'error' })
    } finally {
      rotateKey()
    }
  })

  return { entryId, betPaise, roundId, autoCashout, busy, place, cashout }
}
