import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Handshake } from 'lucide-react'
import { usePermission } from '../../../hooks/usePermission'
import { affAdminApi } from '../../../services/affiliateAdmin.api'

type Totals = { ngr: string; partner_share: string; house_share: string }

/** Affiliate amounts are USD; shown in rupees when the ECB rate is known */
const money = (v: string, perUsd: number) => {
  const n = Number(v) * (perUsd || 1)
  const sign = n < 0 ? '-' : n > 0 ? '+' : ''
  const text = Math.abs(n).toLocaleString(perUsd ? 'en-IN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return perUsd ? `${sign}₹${text}` : `${sign}${text} $`
}
const tone = (v: string) => (Number(v) < 0 ? 'text-rose-400' : Number(v) > 0 ? 'text-emerald-400' : 'text-white')

/**
 * Players who came through partner links, this month: what they lost (+) or won (-), and how
 * that result is split between the partners and the house. Refreshes every minute.
 */
export const PartnerSplitCard: React.FC = () => {
  const { hasPermission, isSuperAdmin } = usePermission()
  const allowed = isSuperAdmin() || hasPermission('aff:partner:read')
  const [totals, setTotals] = useState<Totals | null>(null)
  const [players, setPlayers] = useState<number | null>(null)
  const [perUsd, setPerUsd] = useState(0)

  useEffect(() => {
    if (!allowed) return
    let alive = true
    const load = () => affAdminApi.overview().then((d) => {
      if (!alive) return
      setTotals(d.this_month_totals ?? null)
      setPerUsd(Number(d.inr_per_usd) || 0)
      setPlayers(d.this_month.reduce((a, r) => a + r.registrations, 0))
    }).catch(() => undefined)
    void load()
    const timer = window.setInterval(load, 60000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [allowed])

  if (!allowed || !totals) return null
  return (
    <Link to="/admin/affiliate/statistics" className="block rounded-2xl border border-blue-500/30 bg-gradient-to-r from-blue-950/60 to-dark-card p-4 hover:border-blue-400/60">
      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-blue-200">
        <Handshake className="h-4 w-4" />Partner players this month{players !== null ? ` · ${players} sign-ups` : ''}
        <span className="ml-auto normal-case text-[11px] font-semibold text-blue-300">Details →</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div><div className="text-[11px] text-slate-400">Players' result (house view)</div><div className={`text-lg font-black ${tone(totals.ngr)}`}>{money(totals.ngr, perUsd)}</div></div>
        <div><div className="text-[11px] text-slate-400">Partners' share</div><div className={`text-lg font-black ${tone(totals.partner_share)}`}>{money(totals.partner_share, perUsd)}</div></div>
        <div><div className="text-[11px] text-slate-400">Your (house) share</div><div className={`text-lg font-black ${tone(totals.house_share)}`}>{money(totals.house_share, perUsd)}</div></div>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Green = players lost (profit for partners and you) · red = players won (loss shared by partners and you).</p>
    </Link>
  )
}
