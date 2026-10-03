import React, { useEffect, useRef, useState } from 'react'
import { Minus, Plus, Timer } from 'lucide-react'
import { useTeenPattiRound } from './useTeenPattiRound'
import { PlayingCard } from './PlayingCard'
import { ConnectionStatus } from '../../../components/games/ConnectionStatus'
import { MyBetsHistory } from '../../../components/games/MyBetsHistory'
import { EditableQuickAmounts, useQuickAmounts } from '../../../components/games/EditableQuickAmounts'
import { showToast } from '../../../components/common/Toast'
import { playSound, playWinFor } from '../../../utils/sounds'
import { apiClient } from '../../../services/api'
import { syncWalletBalance } from '../../../services/wallet.api'
import { formatPaiseToRupee, rupeeToPaise } from '../../../utils/formatters'
import { getApiErrorMessage } from '../../../utils/apiError'

type Side = 'A' | 'B'
interface MyBet { side: Side; amount: number }
interface HistoryRound { round_no: number; result?: { winner?: string } }

const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

export const TeenPatti: React.FC = () => {
  const round = useTeenPattiRound()
  const [limits, setLimits] = useState({ min: 1, max: 5000 })
  const [amount, setAmount] = useState(10)
  const [busy, setBusy] = useState(false)
  const [myBets, setMyBets] = useState<{ roundId: string | null; bets: MyBet[] }>({ roundId: null, bets: [] })
  const [history, setHistory] = useState<Array<{ no: number; winner: string }>>([])
  const [historyKey, setHistoryKey] = useState(0)
  const quick = useQuickAmounts('rudra247.teenpatti.quickAmounts', [10, 50, 100, 500])
  const announced = useRef<string | null>(null)

  const clamp = (n: number) => Math.min(limits.max, Math.max(limits.min, Math.round(n)))
  const multiplier = round.payoutX100 / 100
  const betsThisRound = myBets.roundId === round.roundId ? myBets.bets : []

  const loadHistory = () => {
    apiClient.get<HistoryRound[]>('/games/teen_patti/history', { params: { limit: 24 } })
      .then(({ data }) => setHistory(data.flatMap((r) => (r.result?.winner ? [{ no: r.round_no, winner: r.result.winner }] : []))))
      .catch(() => undefined)
  }

  useEffect(() => {
    apiClient.get<{ min_bet: number; max_bet: number }>('/games/teen_patti')
      .then(({ data }) => setLimits({ min: data.min_bet / 100, max: data.max_bet / 100 }))
      .catch(() => undefined)
    loadHistory()
  }, [])

  // After settlement: refresh wallet + history, and tell the player how they did
  useEffect(() => {
    if (!round.settledTick) return
    loadHistory()
    setHistoryKey((k) => k + 1)
    void syncWalletBalance().catch(() => undefined)
    const res = round.result
    if (res && announced.current !== res.roundId && myBets.roundId === res.roundId && myBets.bets.length) {
      announced.current = res.roundId
      const won = res.winner === 'TIE'
        ? myBets.bets.reduce((s, b) => s + b.amount, 0)
        : myBets.bets.filter((b) => b.side === res.winner).reduce((s, b) => s + Math.floor((b.amount * round.payoutX100) / 100), 0)
      const staked = myBets.bets.reduce((s, b) => s + b.amount, 0)
      if (res.winner === 'TIE') playSound('cashout')
      else if (won > 0) playWinFor(won, staked)
      else playSound('lose')
      if (res.winner === 'TIE') showToast({ title: 'Tie — stakes refunded', message: `${formatPaiseToRupee(won)} returned to your wallet.`, type: 'info' })
      else if (won > 0) showToast({ title: `Player ${res.winner} wins!`, message: `You won ${formatPaiseToRupee(won)}.`, type: 'success' })
      else showToast({ title: `Player ${res.winner} wins`, message: 'Better luck next hand.', type: 'warning' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [round.settledTick])

  const placeBet = async (side: Side) => {
    if (!round.roundId || round.phase !== 'betting' || busy) return
    const paise = rupeeToPaise(clamp(amount))
    setBusy(true)
    try {
      await apiClient.post('/games/teen-patti/action', { round_id: round.roundId, amount: paise, side }, { headers: { 'Idempotency-Key': newKey() } })
      setMyBets((m) => ({ roundId: round.roundId, bets: [...(m.roundId === round.roundId ? m.bets : []), { side, amount: paise }] }))
      playSound('bet')
      void syncWalletBalance().catch(() => undefined)
    } catch (error) {
      showToast({ title: 'Bet not placed', message: getApiErrorMessage(error, 'The server rejected this bet.'), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const res = round.phase === 'result' ? round.result : null
  const stakeOn = (side: Side) => betsThisRound.filter((b) => b.side === side).reduce((s, b) => s + b.amount, 0)

  const hand = (side: Side) => {
    const cards = res ? (side === 'A' ? res.playerA : res.playerB) : null
    const handName = res ? (side === 'A' ? res.handA : res.handB) : null
    const winner = res?.winner === side
    const loser = res && res.winner !== side && res.winner !== 'TIE'
    return (
      <div className={`flex-1 rounded-2xl border p-3 text-center transition-all ${winner ? 'border-amber-300 bg-amber-300/10 shadow-[0_0_30px_rgba(252,211,77,0.25)]' : 'border-white/10 bg-black/20'} ${loser ? 'opacity-60' : ''}`}>
        <p className="mb-2 text-sm font-black tracking-wide text-white">PLAYER {side}</p>
        <div className="flex justify-center gap-1.5">
          {[0, 1, 2].map((i) => <PlayingCard key={i} code={cards ? cards[i] : null} delayMs={(side === 'A' ? 0 : 150) + i * 300} highlight={winner} />)}
        </div>
        <p className={`mt-2 h-5 text-xs font-bold ${winner ? 'text-amber-300' : 'text-white/70'}`}>
          {handName ? `${handName}${winner ? ' • WINNER' : ''}` : round.phase === 'locked' ? 'Dealing…' : ''}
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-dark-border bg-dark-card p-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-b from-emerald-600 to-green-900 text-2xl">🃏</span>
          <div>
            <h2 className="text-lg font-black text-white">Teen Patti</h2>
            <span className="text-xs font-mono text-slate-400">Round #{round.roundNo || '—'}</span>
          </div>
        </div>
        <ConnectionStatus connected={round.connected} />
      </div>

      {/* Results strip */}
      <div className="flex gap-1.5 overflow-x-auto rounded-xl bg-dark-card p-2 [scrollbar-width:none]">
        {history.length === 0 ? <span className="px-1 text-xs text-slate-500">No hands yet</span> : history.map((h) => (
          <span key={h.no} title={`Round #${h.no}`} className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-black ${h.winner === 'A' ? 'bg-blue-600 text-white' : h.winner === 'B' ? 'bg-rose-600 text-white' : 'bg-slate-500 text-white'}`}>
            {h.winner === 'TIE' ? 'T' : h.winner}
          </span>
        ))}
      </div>

      {/* Table */}
      <section className="relative overflow-hidden rounded-3xl border border-emerald-900 bg-[radial-gradient(ellipse_at_center,#166534_0%,#14532d_45%,#052e16_100%)] p-3 sm:p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-center">
          {round.phase === 'betting' ? (
            <span className="flex items-center gap-2 rounded-full bg-black/40 px-4 py-1.5 text-sm font-black text-white">
              <Timer className="h-4 w-4 text-amber-300" />Place your bets • <span className={`font-mono ${round.secondsLeft <= 5 ? 'text-rose-300' : 'text-amber-300'}`}>{round.secondsLeft}s</span>
            </span>
          ) : (
            <span className="rounded-full bg-black/40 px-4 py-1.5 text-sm font-black text-white">
              {round.phase === 'result' && res ? (res.winner === 'TIE' ? 'TIE — bets refunded' : `PLAYER ${res.winner} WINS`) : round.phase === 'locked' ? 'Bets closed • dealing' : 'Waiting for next hand…'}
            </span>
          )}
        </div>
        <div className="flex gap-2 sm:gap-4">
          {hand('A')}
          <div className="flex items-center text-sm font-black text-white/60">VS</div>
          {hand('B')}
        </div>
        {round.pool.bets > 0 && (
          <p className="mt-3 text-center text-[11px] text-white/70">
            {round.pool.bets} bets • A {formatPaiseToRupee(round.pool.A)} • B {formatPaiseToRupee(round.pool.B)}
          </p>
        )}
      </section>

      {/* Bet panel */}
      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-3">
        <div className="flex items-center rounded-full bg-black/40 px-1 py-1">
          <button type="button" aria-label="Decrease" onClick={() => setAmount((a) => clamp(a - (a > 100 ? 10 : 1)))} className="flex h-8 w-8 items-center justify-center rounded-full bg-dark-elevated text-slate-200"><Minus className="h-4 w-4" /></button>
          <span className="ml-2 font-bold text-slate-400">₹</span>
          <input
            type="number" inputMode="numeric" value={amount} min={limits.min} max={limits.max}
            onChange={(e) => setAmount(Number(e.target.value) || 0)} onBlur={() => setAmount((a) => clamp(a))}
            aria-label="Bet amount in rupees"
            className="min-w-0 flex-1 bg-transparent text-center font-mono text-lg font-black text-white focus:outline-none"
          />
          <button type="button" aria-label="Increase" onClick={() => setAmount((a) => clamp(a + (a >= 100 ? 10 : 1)))} className="flex h-8 w-8 items-center justify-center rounded-full bg-dark-elevated text-slate-200"><Plus className="h-4 w-4" /></button>
        </div>
        <EditableQuickAmounts amounts={quick.amounts} onSave={quick.save} onReset={quick.reset} onPick={(n) => setAmount(clamp(n))} selected={amount} min={limits.min} max={limits.max} columns={4} />
        <div className="grid grid-cols-2 gap-2">
          {(['A', 'B'] as const).map((side) => (
            <button
              key={side}
              type="button"
              disabled={round.phase !== 'betting' || busy || !round.roundId}
              onClick={() => void placeBet(side)}
              className={`rounded-2xl py-3 text-white shadow-lg transition active:scale-[0.98] disabled:opacity-45 ${side === 'A' ? 'bg-gradient-to-b from-blue-500 to-blue-700' : 'bg-gradient-to-b from-rose-500 to-rose-700'}`}
            >
              <span className="block text-base font-black">PLAYER {side}</span>
              <span className="block text-xs font-bold opacity-90">{multiplier.toFixed(2)}x{stakeOn(side) ? ` • your bet ${formatPaiseToRupee(stakeOn(side))}` : ''}</span>
            </button>
          ))}
        </div>
        <p className="text-center text-[11px] text-slate-500">
          Winning side pays {multiplier.toFixed(2)}x • a tie refunds every bet • Trail &gt; Pure Sequence &gt; Sequence &gt; Color &gt; Pair &gt; High Card
        </p>
      </section>

      <section className="rounded-2xl border border-dark-border bg-dark-card p-3">
        <MyBetsHistory gameId="teen_patti" refreshKey={historyKey} title="My Teen Patti bets" />
      </section>
    </div>
  )
}
