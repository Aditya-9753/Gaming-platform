import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AviatorChart, AVIATOR_COVER_SRC } from './AviatorChart'
import { AviatorBetPanel } from './AviatorBetPanel'
import { AviatorHistory } from './AviatorHistory'
import { useAviatorRound } from './useAviatorRound'
import { useAviatorBet } from './useAviatorBet'
import { ConnectionStatus } from '../../../components/games/ConnectionStatus'
import { ProvablyFairBadge } from '../../../components/games/ProvablyFairBadge'
import { MyBetsHistory } from '../../../components/games/MyBetsHistory'
import { showToast } from '../../../components/common/Toast'
import { formatPaiseToRupee } from '../../../utils/formatters'
import { apiClient } from '../../../services/api'
import { AVIATOR_MILESTONES, onMutedChange, playMilestone, playSound, startEngine, type EngineSound } from '../../../utils/sounds'
import { t as tr } from '../../../i18n'

interface GameLimits { min_bet: number; max_bet: number }

export const Aviator: React.FC = () => {
  const round = useAviatorRound()
  const [history, setHistory] = useState<number[]>([])
  const [limits, setLimits] = useState({ min: 1, max: 5000 })
  const [tab, setTab] = useState<'all' | 'mine'>('all')
  const [historyKey, setHistoryKey] = useState(0)
  const bumpHistory = useCallback(() => setHistoryKey((k) => k + 1), [])
  const slotA = useAviatorBet(round, 'Bet 1', bumpHistory)
  const slotB = useAviatorBet(round, 'Bet 2', bumpHistory)

  useEffect(() => {
    apiClient.get<GameLimits>('/games/aviator')
      .then(({ data }) => setLimits({ min: data.min_bet / 100, max: data.max_bet / 100 }))
      .catch(() => showToast({ title: tr('Could not load limits'), message: tr('Bet limits could not be fetched from the game server.'), type: 'error' }))
    apiClient.get<Array<{ round_no: number; result?: { crash_point?: number } }>>('/games/aviator/history', { params: { limit: 30 } })
      .then(({ data }) => setHistory(data.flatMap((item) => item.result?.crash_point ? [item.result.crash_point] : [])))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (round.phase === 'crashed') setHistory((items) => [round.multiplier, ...items].slice(0, 30))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [round.phase])

  // Engine drone while the plane flies; pitch follows the multiplier; whoosh when it flies away
  const engine = useRef<EngineSound | null>(null)
  useEffect(() => {
    if (round.phase === 'flying') {
      if (!engine.current) {
        playSound('takeoff')
        engine.current = startEngine()
      }
    } else if (engine.current) {
      engine.current.stop(round.phase === 'crashed')
      engine.current = null
    }
  }, [round.phase])
  // Milestone chimes (2x, 5x, 10x ...) once per round while the plane climbs
  const nextMilestone = useRef(0)
  useEffect(() => {
    if (round.phase !== 'flying') { nextMilestone.current = 0; return }
    engine.current?.setMultiplier(round.multiplier)
    while (nextMilestone.current < AVIATOR_MILESTONES.length && round.multiplier >= AVIATOR_MILESTONES[nextMilestone.current]) {
      if (round.multiplier < AVIATOR_MILESTONES[nextMilestone.current] * 1.15) playMilestone(AVIATOR_MILESTONES[nextMilestone.current])
      nextMilestone.current += 1
    }
  }, [round.multiplier, round.phase])
  // "Place your bets" chime when a round opens, ticks in the last 3 seconds of betting
  useEffect(() => { if (round.phase === 'betting') playSound('roundOpen') }, [round.phase])
  useEffect(() => {
    if (round.phase === 'betting' && round.countdown > 0 && round.countdown <= 3) playSound('countdown')
  }, [round.countdown, round.phase])
  useEffect(() => onMutedChange((muted) => {
    if (muted) engine.current = null // setMuted already silenced it
    else if (round.phase === 'flying' && !engine.current) engine.current = startEngine()
  }), [round.phase])
  useEffect(() => () => { engine.current?.stop(false); engine.current = null }, [])

  const totalBets = round.bets.reduce((sum, b) => sum + b.amount, 0)

  return (
    <div className="space-y-3 max-w-5xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 bg-dark-card border border-dark-border p-3 rounded-2xl">
        <div className="flex items-center gap-3">
          <img src={AVIATOR_COVER_SRC} alt="" className="w-16 h-11 rounded-lg object-cover shadow-md" />
          <div>
            <h2 className="text-lg font-black text-white">{tr('Aviator')}</h2>
            <span className="text-xs font-mono text-slate-400">Round #{round.roundNumber || '—'}</span>
          </div>
        </div>
        <div className="flex items-center gap-3"><ConnectionStatus connected={round.connected} /><ProvablyFairBadge /></div>
      </div>

      <AviatorHistory history={history} />
      <AviatorChart multiplier={round.multiplier} phase={round.phase} countdown={round.countdown} bettingTotal={round.bettingTotal} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {[slotA, slotB].map((slot, index) => (
          <AviatorBetPanel
            key={index}
            slot={slot}
            phase={round.phase}
            multiplier={round.multiplier}
            roundId={round.roundId}
            minRupees={limits.min}
            maxRupees={limits.max}
          />
        ))}
      </div>

      <section className="rounded-2xl bg-[#1b1c1d] border border-white/5 p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="inline-flex rounded-full bg-black/40 p-0.5 text-xs font-bold">
            <button type="button" onClick={() => setTab('all')} className={`px-4 py-1 rounded-full ${tab === 'all' ? 'bg-[#2c2d30] text-white' : 'text-slate-400'}`}>{tr('All bets')}</button>
            <button type="button" onClick={() => setTab('mine')} className={`px-4 py-1 rounded-full ${tab === 'mine' ? 'bg-[#2c2d30] text-white' : 'text-slate-400'}`}>{tr('My history')}</button>
          </div>
          {tab === 'all' && <span className="text-xs text-slate-400">{round.bets.length} bets • {formatPaiseToRupee(totalBets)}</span>}
        </div>

        {tab === 'all' ? (
          round.bets.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-400">{tr('No bets in this round yet.')}</p>
          ) : (
            <div className="max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-1.5 font-semibold">{tr('Player')}</th><th className="py-1.5 font-semibold text-right">{tr('Bet')}</th><th className="py-1.5 font-semibold text-right">{tr('X')}</th><th className="py-1.5 font-semibold text-right">{tr('Win')}</th></tr></thead>
                <tbody>
                  {round.bets.map((bet) => (
                    <tr key={bet.entryId} className={`border-t border-white/5 ${bet.cashedAt ? 'bg-emerald-500/10' : ''}`}>
                      <td className="py-1.5 text-slate-300">{bet.player}</td>
                      <td className="py-1.5 text-right font-mono text-slate-200">{formatPaiseToRupee(bet.amount)}</td>
                      <td className="py-1.5 text-right font-mono font-bold text-violet-300">{bet.cashedAt ? `${bet.cashedAt.toFixed(2)}x` : ''}</td>
                      <td className="py-1.5 text-right font-mono text-emerald-400">{bet.payout ? formatPaiseToRupee(bet.payout) : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          <MyBetsHistory gameId="aviator" refreshKey={historyKey} />
        )}
      </section>
    </div>
  )
}
