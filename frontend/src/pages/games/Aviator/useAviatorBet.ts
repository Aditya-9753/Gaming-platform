import { useCallback, useEffect, useRef, useState } from 'react'
import type { AviatorState } from './useAviatorRound'
import { apiClient } from '../../../services/api'
import { useIdempotencyKey } from '../../../hooks/useIdempotencyKey'
import { syncWalletBalance } from '../../../services/wallet.api'
import { showToast } from '../../../components/common/Toast'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'

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
    clear()
    refreshWallet()
    onSettled?.()
    showToast({
      title: cashout.automatic ? `${label}: auto cashout!` : `${label}: cashed out!`,
      message: `Won ${formatPaiseToRupee(cashout.payout)} at ${cashout.multiplier.toFixed(2)}x.`,
      type: 'success',
    })
  }, [round.lastCashout, entryId, clear, label, onSettled])

  // Plane flew away with this bet still riding
  useEffect(() => {
    if (round.phase !== 'crashed' || betPaise === null || roundId !== round.roundId) return
    showToast({ title: `${label}: flew away`, message: `Lost ${formatPaiseToRupee(betPaise)} at ${round.multiplier.toFixed(2)}x.`, type: 'error' })
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
      showToast({ title: `${label}: bet placed`, message: `${formatPaiseToRupee(data.bet_amount)} on round #${round.roundNumber}${auto ? ` • auto ${auto.toFixed(2)}x` : ''}.`, type: 'success' })
    } catch (error) {
      showToast({ title: `${label}: bet rejected`, message: getApiErrorMessage(error, 'The server rejected this bet.'), type: 'error' })
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
      clear()
      refreshWallet()
      onSettled?.()
      showToast({ title: `${label}: cashed out!`, message: `Won ${formatPaiseToRupee(data.payout_amount)} at ${data.multiplier.toFixed(2)}x.`, type: 'success' })
    } catch (error) {
      showToast({ title: `${label}: cashout failed`, message: getApiErrorMessage(error, 'The plane may have already flown away.'), type: 'error' })
    } finally {
      rotateKey()
    }
  })

  return { entryId, betPaise, roundId, autoCashout, busy, place, cashout }
}
