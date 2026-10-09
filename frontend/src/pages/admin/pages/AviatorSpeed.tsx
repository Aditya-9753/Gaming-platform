import React, { useEffect, useMemo, useState } from 'react'
import { Gauge, Plane, RotateCcw, Save, Timer } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { Btn, Card, ErrorBox, Spinner, cx, errorText } from '../../../components/affiliate/ui'
import { showToast } from '../../../components/common/Toast'

interface SpeedView {
  exp_growth_rate: number
  seconds_to: Record<string, number>
  betting_duration_sec: number
  intermission_sec: number
  presets: Array<{ id: string; label: string; rate: number; seconds_to: Record<string, number> }>
  limits: { rate: [number, number]; betting_duration_sec: [number, number]; intermission_sec: [number, number] }
}

const MILESTONES = [2, 5, 10, 100]
const secondsTo = (rate: number, m: number) => Math.log(m) / rate

/** Super admin: how fast the Aviator plane climbs, plus betting time and the break between rounds. */
export const AviatorSpeed: React.FC = () => {
  const [view, setView] = useState<SpeedView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [twoX, setTwoX] = useState(7.7)
  const [betting, setBetting] = useState(6)
  const [pause, setPause] = useState(2)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const { data } = await apiClient.get<SpeedView>('/admin/aviator/speed')
      setView(data)
      setTwoX(Number(secondsTo(data.exp_growth_rate, 2).toFixed(1)))
      setBetting(data.betting_duration_sec)
      setPause(data.intermission_sec)
      setError(null)
    } catch (e) {
      setError(errorText(e, 'Could not load the Aviator speed'))
    }
  }
  useEffect(() => { void load() }, [])

  const rate = Math.log(2) / twoX
  const preview = useMemo(() => MILESTONES.map((m) => ({ m, s: secondsTo(rate, m) })), [rate])
  if (error) return <ErrorBox message={error} onRetry={load} />
  if (!view) return <Spinner />

  const [minRate, maxRate] = view.limits.rate
  const minTwoX = Math.ceil((Math.log(2) / maxRate) * 10) / 10
  const maxTwoX = Math.floor((Math.log(2) / minRate) * 10) / 10
  const currentTwoX = secondsTo(view.exp_growth_rate, 2)
  const dirty = Math.abs(twoX - currentTwoX) > 0.05 || betting !== view.betting_duration_sec || pause !== view.intermission_sec
  const relative = currentTwoX / twoX

  const save = async () => {
    setBusy(true)
    try {
      const { data } = await apiClient.put<SpeedView>('/admin/aviator/speed', {
        seconds_to_2x: twoX, betting_duration_sec: betting, intermission_sec: pause,
      })
      setView(data)
      showToast({ title: 'Aviator speed saved', message: 'Applies from the next round.', type: 'success' })
    } catch (e) {
      showToast({ title: 'Not saved', message: errorText(e), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Plane className="h-7 w-7 text-rose-400" />
        <div>
          <h1 className="text-xl font-black text-white">Aviator Speed</h1>
          <p className="text-xs text-slate-400">Super admin only. Changes apply from the next round; a plane already flying keeps its speed.
            Speed never changes where a round crashes — that is fixed by the provably fair seeds.</p>
        </div>
      </div>

      <Card title="Presets">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {view.presets.map((p) => {
            const active = Math.abs(secondsTo(p.rate, 2) - twoX) < 0.05
            return (
              <button key={p.id} type="button" onClick={() => setTwoX(Number(secondsTo(p.rate, 2).toFixed(1)))}
                className={cx('rounded-xl border p-3 text-left transition', active ? 'border-brand-blue bg-brand-blue/15' : 'border-dark-border bg-dark-bg hover:border-slate-500')}>
                <div className="text-sm font-black text-white">{p.label}</div>
                <div className="text-[11px] text-slate-400">2x in {p.seconds_to['2x']} s</div>
              </button>
            )
          })}
        </div>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Gauge className="h-4 w-4" />Flight speed</span>}>
        <div className="space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-slate-300">Time to reach <b>2x</b></span>
            <span className="text-2xl font-black text-white tabular-nums">{twoX.toFixed(1)} s</span>
          </div>
          <input type="range" min={minTwoX} max={maxTwoX} step={0.1} value={twoX} onChange={(e) => setTwoX(Number(e.target.value))}
            className="w-full accent-rose-500" aria-label="Seconds to reach 2x" />
          <div className="flex justify-between text-[11px] text-slate-500"><span>Faster ({minTwoX}s)</span><span>Slower ({maxTwoX}s)</span></div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {preview.map(({ m, s }) => (
              <div key={m} className="rounded-xl bg-dark-bg p-3 text-center">
                <div className="text-[11px] text-slate-500">{m}x reached in</div>
                <div className="text-lg font-black text-white tabular-nums">{s.toFixed(1)} s</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">
            Live now: 2x in {currentTwoX.toFixed(1)} s.{' '}
            {Math.abs(relative - 1) > 0.01 && <b className={relative > 1 ? 'text-emerald-300' : 'text-amber-300'}>
              New setting is {relative > 1 ? `${relative.toFixed(2)}× faster` : `${(1 / relative).toFixed(2)}× slower`}.</b>}
          </p>
        </div>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Timer className="h-4 w-4" />Round timing</span>}>
        <div className="grid gap-5 sm:grid-cols-2">
          <label className="block space-y-2">
            <span className="flex justify-between text-sm text-slate-300"><span>Betting time</span><b className="text-white">{betting} s</b></span>
            <input type="range" min={view.limits.betting_duration_sec[0]} max={view.limits.betting_duration_sec[1]} step={1} value={betting}
              onChange={(e) => setBetting(Number(e.target.value))} className="w-full accent-brand-blue" />
            <span className="text-[11px] text-slate-500">How long players can place bets before take-off.</span>
          </label>
          <label className="block space-y-2">
            <span className="flex justify-between text-sm text-slate-300"><span>Break between rounds</span><b className="text-white">{pause} s</b></span>
            <input type="range" min={view.limits.intermission_sec[0]} max={view.limits.intermission_sec[1]} step={1} value={pause}
              onChange={(e) => setPause(Number(e.target.value))} className="w-full accent-brand-blue" />
            <span className="text-[11px] text-slate-500">Pause after the plane flies away, before the next betting window.</span>
          </label>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Btn busy={busy} disabled={!dirty} onClick={save}><Save className="h-4 w-4" />Save</Btn>
        <Btn tone="ghost" disabled={!dirty || busy} onClick={() => {
          setTwoX(Number(currentTwoX.toFixed(1))); setBetting(view.betting_duration_sec); setPause(view.intermission_sec)
        }}><RotateCcw className="h-4 w-4" />Undo changes</Btn>
      </div>
    </div>
  )
}
