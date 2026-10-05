import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Gamepad2, Info, Palette, Percent, Save, Wrench } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { showToast } from '../../../components/common/Toast'
import { Button } from '../../../components/common/Button'
import { Input } from '../../../components/common/Input'
import { getApiErrorMessage } from '../../../utils/apiError'
import { refreshPlatformConfig } from '../../../hooks/usePlatformConfig'

interface SystemValues {
  platform_name: string
  platform_logo_url: string
  maintenance_mode: boolean
  maintenance_message: string
  signup_bonus_paise: number
  daily_claim_amount_paise: number
}

interface GameSettings { game_id: string; name: string; is_active: boolean; min_bet: number; max_bet: number; house_edge_percent: number; config: Record<string, unknown>; supports_margin?: boolean }

const LIMIT_GAMES = ['aviator', 'mines', 'color', 'wingo_30s', 'wingo_1m', 'wingo_3m', 'wingo_5m', 'cricket']
const WINGO = ['wingo_30s', 'wingo_1m', 'wingo_3m', 'wingo_5m']

const PAYOUT_FIELDS: Array<[string, string]> = [
  ['GREEN', 'Green (1,3,7,9)'], ['RED', 'Red (2,4,6,8)'], ['COLOR_HALF', 'Green on 5 / Red on 0'],
  ['VIOLET', 'Violet (0,5)'], ['NUMBER', 'Exact number'], ['SIZE', 'Big / Small'],
]
// One margin per game, sent as house_edge_percent (basis points). Aviator / Mines use it in
// their formula; the server recalculates WinGo, Color and Teen Patti payouts from it.
// Teen Patti also has 2 equal sides, so its margin is read back as 1 - payout / 2.
const MARGIN_GAMES: Array<{ id: string; label: string; hint: string; targets?: string[] }> = [
  { id: 'aviator', label: 'Aviator', hint: 'Crash points are scaled so players get back this much less on average.' },
  { id: 'mines', label: 'Mines', hint: 'Every gem multiplier is reduced by this margin.' },
  { id: 'wingo_30s', label: 'WinGo (all modes)', hint: 'Every pick’s multiplier is recalculated to this margin (overwrites the table below).', targets: WINGO },
  { id: 'color', label: 'Color Prediction', hint: 'Red, Green and Violet payouts are recalculated to this margin.' },
  { id: 'teen_patti', label: 'Teen Patti', hint: 'Sets the winning side payout: 2 × (1 − margin).' },
]
const MAX_MARGIN_PCT = 50

const DEFAULT_PAYOUTS: Record<string, number> = { GREEN: 2, RED: 2, COLOR_HALF: 1.5, VIOLET: 4.5, NUMBER: 9, SIZE: 1.96 }

const Section: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode; hint?: string }> = ({ title, icon, children, hint }) => (
  <section className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-5">
    <div>
      <h2 className="flex items-center gap-2 text-base font-black text-white">{icon}{title}</h2>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
    {children}
  </section>
)

/** WinGo house edge per pick type, from the payout table (10 equally likely numbers). */
const rtp = (p: Record<string, number>) => ({
  GREEN: (4 * p.GREEN + p.COLOR_HALF) / 10,
  RED: (4 * p.RED + p.COLOR_HALF) / 10,
  VIOLET: (2 * p.VIOLET) / 10,
  NUMBER: p.NUMBER / 10,
  SIZE: (5 * p.SIZE) / 10,
})

export const AdminSettings: React.FC = () => {
  const [values, setValues] = useState<SystemValues | null>(null)
  const [games, setGames] = useState<Record<string, GameSettings>>({})
  const [payouts, setPayouts] = useState<Record<string, number>>(DEFAULT_PAYOUTS)
  const [saving, setSaving] = useState<string | null>(null)
  const [margins, setMargins] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      const { data } = await apiClient.get<{ values: SystemValues }>('/admin/system-settings')
      setValues(data.values)
      const loaded = await Promise.all(LIMIT_GAMES.map((id) => apiClient.get<GameSettings>(`/admin/games/${id}/settings`).then((r) => r.data).catch(() => null)))
      const map: Record<string, GameSettings> = {}
      loaded.forEach((g) => { if (g) map[g.game_id] = g })
      setGames(map)
      // House margins: Aviator / Mines house edge, Teen Patti from its payout
      const marginRows = await Promise.all(MARGIN_GAMES.map(({ id }) => apiClient.get<GameSettings>(`/admin/games/${id}/settings`).then((r) => r.data).catch(() => null)))
      const next: Record<string, string> = {}
      marginRows.forEach((g) => {
        if (!g) return
        if (g.game_id === 'teen_patti') {
          const payout = Number((g.config?.payout as number | undefined) ?? 1.96)
          next[g.game_id] = String(Math.round((1 - payout / 2) * 10000) / 100)
        } else next[g.game_id] = String(g.house_edge_percent / 100)
      })
      setMargins(next)
      const wingoPayouts = map.wingo_30s?.config?.payouts as Record<string, number> | undefined
      setPayouts({ ...DEFAULT_PAYOUTS, ...(wingoPayouts ?? {}) })
    } catch (error) {
      showToast({ title: 'Settings unavailable', message: getApiErrorMessage(error, 'Only the super admin can change platform settings.'), type: 'error' })
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const saveSystem = async (patch: Partial<SystemValues>, label: string) => {
    setSaving(label)
    try {
      const { data } = await apiClient.put<{ values: SystemValues }>('/admin/system-settings', { values: patch })
      setValues(data.values)
      await refreshPlatformConfig()
      showToast({ title: `${label} saved`, message: 'Applied across the site and recorded in the audit log.', type: 'success' })
    } catch (error) {
      showToast({ title: 'Could not save', message: getApiErrorMessage(error, 'Please check the values.'), type: 'error' })
    } finally {
      setSaving(null)
    }
  }

  const saveLimits = async () => {
    setSaving('limits')
    try {
      for (const id of LIMIT_GAMES) {
        const g = games[id]
        if (g) await apiClient.patch(`/admin/games/${id}/settings`, { min_bet: g.min_bet, max_bet: g.max_bet })
      }
      showToast({ title: 'Entry limits saved', message: 'New limits apply to the next bets.', type: 'success' })
      await load()
    } catch (error) {
      showToast({ title: 'Could not save limits', message: getApiErrorMessage(error, 'Check that min is below max.'), type: 'error' })
    } finally {
      setSaving(null)
    }
  }

  const saveMargins = async () => {
    for (const { id, label } of MARGIN_GAMES) {
      const pct = Number(margins[id])
      if (margins[id] === undefined) continue
      if (!Number.isFinite(pct) || pct < 0 || pct > MAX_MARGIN_PCT) {
        showToast({ title: `${label}: invalid margin`, message: `Enter a margin between 0% and ${MAX_MARGIN_PCT}%.`, type: 'error' })
        return
      }
    }
    setSaving('margins')
    try {
      for (const { id, targets } of MARGIN_GAMES) {
        if (margins[id] === undefined) continue
        const bp = Math.round(Number(margins[id]) * 100)
        const body: Record<string, unknown> = { house_edge_percent: bp }
        if (id === 'teen_patti') body.config = { payout: Math.floor(2 * (1 - bp / 10000) * 100) / 100 }
        for (const target of targets ?? [id]) await apiClient.patch(`/admin/games/${target}/settings`, body)
      }
      showToast({ title: 'House margins saved', message: 'Applied from the next round and recorded in the audit log.', type: 'success' })
      await load()
    } catch (error) {
      showToast({ title: 'Could not save margins', message: getApiErrorMessage(error, 'Check the values.'), type: 'error' })
    } finally {
      setSaving(null)
    }
  }

  const savePayouts = async () => {
    setSaving('payouts')
    try {
      for (const id of WINGO) await apiClient.patch(`/admin/games/${id}/settings`, { config: { payouts } })
      showToast({ title: 'WinGo multipliers saved', message: 'Used from the next period of every WinGo mode.', type: 'success' })
      await load()
    } catch (error) {
      showToast({ title: 'Could not save multipliers', message: getApiErrorMessage(error, 'Each multiplier must be between 1x and 100x.'), type: 'error' })
    } finally {
      setSaving(null)
    }
  }


  const setGame = (id: string, field: 'min_bet' | 'max_bet', rupees: string) =>
    setGames((g) => ({ ...g, [id]: { ...g[id], [field]: Math.round(Number(rupees) * 100) || 0 } }))

  if (!values) return <p className="text-sm text-slate-400">Loading settings…</p>
  const returns = rtp(payouts)

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Platform Settings</h1>
        <p className="text-xs text-slate-400">Branding, maintenance, credit amounts, entry limits and WinGo reward multipliers. Every change is audit logged.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Branding" icon={<Palette className="h-4 w-4 text-purple-400" />}>
          <Input label="Platform name" value={values.platform_name} maxLength={40} onChange={(e) => setValues({ ...values, platform_name: e.target.value })} />
          <Input label="Logo URL" placeholder="https://… or /logo.png (empty = default)" value={values.platform_logo_url} onChange={(e) => setValues({ ...values, platform_logo_url: e.target.value })} />
          {values.platform_logo_url && <img src={values.platform_logo_url} alt="Logo preview" className="h-12 w-12 rounded-xl bg-dark-elevated object-contain p-1" />}
          <Button type="button" leftIcon={<Save className="h-4 w-4" />} isLoading={saving === 'Branding'} onClick={() => void saveSystem({ platform_name: values.platform_name, platform_logo_url: values.platform_logo_url }, 'Branding')}>Save branding</Button>
        </Section>

        <Section title="Maintenance mode" icon={<Wrench className="h-4 w-4 text-amber-400" />} hint="While on, players cannot place new bets (admins can still test). A banner shows on every page.">
          <label className="flex items-center justify-between rounded-xl bg-dark-elevated px-4 py-3">
            <span className="text-sm font-bold text-white">{values.maintenance_mode ? 'Maintenance is ON' : 'Platform is live'}</span>
            <button
              type="button"
              role="switch"
              aria-checked={values.maintenance_mode}
              onClick={() => void saveSystem({ maintenance_mode: !values.maintenance_mode, maintenance_message: values.maintenance_message }, 'Maintenance mode')}
              className={`relative h-7 w-12 rounded-full transition ${values.maintenance_mode ? 'bg-amber-500' : 'bg-slate-600'}`}
            >
              <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${values.maintenance_mode ? 'left-6' : 'left-1'}`} />
            </button>
          </label>
          <Input label="Banner message" value={values.maintenance_message} maxLength={300} onChange={(e) => setValues({ ...values, maintenance_message: e.target.value })} />
          <Button type="button" variant="secondary" isLoading={saving === 'Maintenance message'} onClick={() => void saveSystem({ maintenance_message: values.maintenance_message }, 'Maintenance message')}>Save message</Button>
        </Section>

        <Section title="Virtual credit amounts" icon={<Info className="h-4 w-4 text-emerald-400" />}>
          <Input label="Sign-up bonus (₹)" type="number" min={0} value={values.signup_bonus_paise / 100} onChange={(e) => setValues({ ...values, signup_bonus_paise: Math.round(Number(e.target.value) * 100) })} />
          <Input label="Daily bonus (₹)" type="number" min={0} value={values.daily_claim_amount_paise / 100} onChange={(e) => setValues({ ...values, daily_claim_amount_paise: Math.round(Number(e.target.value) * 100) })} />
          <Button type="button" leftIcon={<Save className="h-4 w-4" />} isLoading={saving === 'Credit amounts'} onClick={() => void saveSystem({ signup_bonus_paise: values.signup_bonus_paise, daily_claim_amount_paise: values.daily_claim_amount_paise }, 'Credit amounts')}>Save amounts</Button>
        </Section>

        <Section title="Real money & payments" icon={<AlertTriangle className="h-4 w-4 text-rose-400" />}>
          <p className="text-xs leading-relaxed text-slate-400">This platform runs on <b className="text-white">virtual credits only</b>. Deposits, withdrawals and payment-gateway keys are intentionally not supported: real-money online betting games are prohibited in India (Promotion and Regulation of Online Gaming Act, 2025).</p>
        </Section>
      </div>

      <Section title="Entry limits (min / max bet)" icon={<Gamepad2 className="h-4 w-4 text-sky-400" />} hint="Amounts in ₹. Applies to new bets immediately.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm">
            <thead><tr className="text-left text-xs text-slate-400"><th className="py-2">Game</th><th className="py-2">Min (₹)</th><th className="py-2">Max (₹)</th></tr></thead>
            <tbody>
              {LIMIT_GAMES.filter((id) => games[id]).map((id) => (
                <tr key={id} className="border-t border-dark-border/60">
                  <td className="py-2 pr-3 font-bold text-white">{games[id].name}</td>
                  <td className="py-2 pr-3"><input type="number" min={1} aria-label={`${id} minimum`} value={games[id].min_bet / 100} onChange={(e) => setGame(id, 'min_bet', e.target.value)} className="w-28 rounded-lg border border-dark-border bg-dark-elevated px-2 py-1.5 text-white" /></td>
                  <td className="py-2"><input type="number" min={1} aria-label={`${id} maximum`} value={games[id].max_bet / 100} onChange={(e) => setGame(id, 'max_bet', e.target.value)} className="w-28 rounded-lg border border-dark-border bg-dark-elevated px-2 py-1.5 text-white" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button type="button" leftIcon={<Save className="h-4 w-4" />} isLoading={saving === 'limits'} onClick={() => void saveLimits()}>Save limits</Button>
      </Section>

      <Section title="House margin" icon={<Percent className="h-4 w-4 text-amber-400" />} hint="The share of stakes the house keeps on average (RTP = 100% − margin). Only payouts change; results stay seed-driven and never look at bets. Applies from the next round.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MARGIN_GAMES.map(({ id, label, hint }) => {
            const pct = Number(margins[id] ?? 0)
            const loaded = margins[id] !== undefined
            return (
              <div key={id} className="space-y-2 rounded-xl bg-dark-elevated p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold text-white">{label}</span>
                  {loaded && <span className="rounded-full bg-dark-card px-2 py-0.5 text-[11px] font-bold text-emerald-300">RTP {(100 - pct).toFixed(1)}%</span>}
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  <input
                    type="number" step="0.1" min={0} max={MAX_MARGIN_PCT} disabled={!loaded}
                    value={margins[id] ?? ''} placeholder={loaded ? '' : 'n/a'}
                    onChange={(e) => setMargins((m) => ({ ...m, [id]: e.target.value }))}
                    aria-label={`${label} house margin percent`}
                    className="w-24 rounded-lg border border-dark-border bg-dark-card px-2 py-1.5 text-white disabled:opacity-50"
                  />
                  % margin
                </label>
                {id === 'teen_patti' && loaded && <p className="text-[11px] text-slate-300">Winning side pays {(2 * (1 - pct / 100)).toFixed(2)}x</p>}
                <p className="text-[11px] text-slate-500">{hint}</p>
              </div>
            )
          })}
        </div>
        <Button type="button" leftIcon={<Save className="h-4 w-4" />} isLoading={saving === 'margins'} onClick={() => void saveMargins()}>Save margins</Button>
      </Section>

      <Section title="WinGo reward multipliers" icon={<Gamepad2 className="h-4 w-4 text-rose-400" />} hint="Payout for a winning pick (x stake). Applies to every WinGo mode from the next period; result popups use the live table. Saving a WinGo house margin above recalculates these.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PAYOUT_FIELDS.map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1 rounded-xl bg-dark-elevated p-3 text-xs text-slate-300">
              <span className="font-bold text-white">{label}</span>
              <span className="flex items-center gap-1">
                <input type="number" step="0.01" min={1} max={100} value={payouts[key]} onChange={(e) => setPayouts((p) => ({ ...p, [key]: Number(e.target.value) }))} className="w-24 rounded-lg border border-dark-border bg-dark-card px-2 py-1.5 text-white" />
                <span>x</span>
              </span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          {Object.entries(returns).map(([k, v]) => (
            <span key={k} className={`rounded-full px-2.5 py-1 font-bold ${v > 1 ? 'bg-rose-500/20 text-rose-300' : 'bg-dark-elevated text-slate-300'}`}>{k}: RTP {(v * 100).toFixed(1)}%{v > 1 ? ' (house loses)' : ''}</span>
          ))}
        </div>
        <Button type="button" leftIcon={<Save className="h-4 w-4" />} isLoading={saving === 'payouts'} onClick={() => void savePayouts()}>Save multipliers</Button>
      </Section>
    </div>
  )
}

export const Settings = AdminSettings
