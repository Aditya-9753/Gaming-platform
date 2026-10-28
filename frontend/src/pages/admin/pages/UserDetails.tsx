import React, { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Ban, CheckCircle2, Coins, Handshake, KeyRound, Phone } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/toastBus'
import { apiClient } from '../../../services/api'
import { getApiErrorMessage } from '../../../utils/apiError'
import { formatDateTime, formatPaiseToRupee } from '../../../utils/formatters'

interface UserDetail {
  id: string
  username: string
  email: string | null
  phone: string | null
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
  wallet: { balance: number; locked_balance: number; is_frozen: boolean } | null
  self_exclusion: { ends_at: string } | null
  play: { bets: number; staked_paise: number; won_paise: number; player_profit_paise: number }
  referred_by: { partner_id: number; partner_code: string; registered_at: string | null } | null
}

interface Entry { entry_id: string; game_id: string | null; round_no: number | null; bet_amount: number; payout_amount: number; status: string; created_at: string }

const GAME_NAMES: Record<string, string> = { aviator: 'Aviator', color: 'Color Prediction', mines: 'Mines', 'teen-patti': 'Teen Patti', teenpatti: 'Teen Patti' }

/** One player: who they are, what they played, and who referred them (all live data). */
export const UserDetails: React.FC = () => {
  const { id = '' } = useParams()
  const [user, setUser] = useState<UserDetail | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [detail, history] = await Promise.all([
        apiClient.get<UserDetail>(`/admin/users/${encodeURIComponent(id)}`),
        apiClient.get<{ items: Entry[] }>(`/admin/users/${encodeURIComponent(id)}/history`, { params: { page_size: 15 } }),
      ])
      setUser(detail.data)
      setEntries(history.data.items)
      setError(null)
    } catch (e) {
      setError(getApiErrorMessage(e, 'Could not load this player'))
    }
  }, [id])
  // oxlint-disable-next-line react/set-state-in-effect -- loads data from the server
  useEffect(() => { void load() }, [load])

  const toggleSuspend = async () => {
    if (!user) return
    const reason = window.prompt(user.is_active ? 'Reason for suspending this account' : 'Reason for re-activating this account')
    if (!reason || reason.trim().length < 3) return
    setBusy(true)
    try {
      await apiClient.patch(`/admin/users/${encodeURIComponent(user.id)}/status`, { is_active: !user.is_active, reason: reason.trim() })
      showToast({ title: user.is_active ? 'Account suspended' : 'Account re-activated', type: user.is_active ? 'warning' : 'success' })
      await load()
    } catch (e) {
      showToast({ title: 'Not changed', message: getApiErrorMessage(e, 'Please try again.'), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  // Most players have no email, so the emailed reset link cannot reach them: support sets a temporary password
  const resetPassword = async () => {
    if (!user) return
    if (!window.confirm(`Give ${user.phone ? `+91 ${user.phone.slice(3)}` : user.username} a new temporary password? They will be signed out everywhere.`)) return
    setBusy(true)
    try {
      const { data } = await apiClient.post<{ temporary_password: string }>(`/admin/users/${encodeURIComponent(user.id)}/reset-password`)
      setTempPassword(data.temporary_password)
    } catch (e) {
      showToast({ title: 'Password not reset', message: getApiErrorMessage(e, 'Please try again.'), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const back = (
    <Link to="/admin/users" className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white">
      <ArrowLeft className="w-4 h-4" /><span>Back to User List</span>
    </Link>
  )
  if (error) return <div className="space-y-4 max-w-3xl">{back}<p className="rounded-xl bg-rose-500/10 p-4 text-sm text-rose-300">{error}</p></div>
  if (!user) return <div className="space-y-4 max-w-3xl">{back}<p className="text-sm text-slate-400">Loading…</p></div>

  const profit = user.play.player_profit_paise
  const phone = user.phone ? `+91 ${user.phone.slice(3)}` : null

  return (
    <div className="space-y-6 max-w-3xl">
      {back}
      <div className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-purple-500/20 text-purple-400 flex items-center justify-center text-xl font-bold">
              {user.username[0]?.toUpperCase()}
            </div>
            <div>
              <h2 className="text-xl font-black text-white">{phone || user.username}</h2>
              <span className="text-xs text-slate-400">
                {phone ? <><Phone className="inline w-3 h-3" /> {user.username} · </> : null}
                {user.email || 'no email'} · ID {user.id.slice(0, 8)} · {user.role}
              </span>
              {!user.is_active && <span className="ml-2 rounded bg-rose-500/20 px-1.5 text-[10px] font-bold text-rose-300">SUSPENDED</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {user.role.toUpperCase() === 'USER' && (
              <Button variant="secondary" size="sm" onClick={resetPassword} isLoading={busy} leftIcon={<KeyRound className="w-3.5 h-3.5" />}>
                Reset Password
              </Button>
            )}
            <Button variant={user.is_active ? 'danger' : 'primary'} size="sm" onClick={toggleSuspend} isLoading={busy}
              leftIcon={user.is_active ? <Ban className="w-3.5 h-3.5" /> : <CheckCircle2 className="w-3.5 h-3.5" />}>
              {user.is_active ? 'Suspend Account' : 'Re-activate'}
            </Button>
          </div>
        </div>

        {tempPassword && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            <p>New temporary password (shown only once):</p>
            <p className="mt-1 select-all font-mono text-2xl font-black tracking-wider text-white">{tempPassword}</p>
            <p className="mt-1 text-xs text-emerald-200/80">Tell the player to sign in with their mobile number and this password, then change it in Profile.</p>
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Balance" value={formatPaiseToRupee(user.wallet?.balance ?? 0)} tone="text-emerald-400" />
          <Stat label="Bets placed" value={String(user.play.bets)} />
          <Stat label="Staked / won" value={`${formatPaiseToRupee(user.play.staked_paise, false)} / ${formatPaiseToRupee(user.play.won_paise, false)}`} small />
          <Stat label="Player profit / loss" value={`${profit > 0 ? '+' : ''}${formatPaiseToRupee(profit, false)}`} tone={profit > 0 ? 'text-rose-300' : profit < 0 ? 'text-emerald-400' : 'text-white'} />
        </div>
        <p className="text-[11px] text-slate-500">
          Player profit is what the house lost to this player ({profit > 0 ? 'the player is winning' : profit < 0 ? 'the house is winning' : 'even'}).
          Joined {formatDateTime(user.created_at)} · last sign-in {user.last_login_at ? formatDateTime(user.last_login_at) : '—'}
          {user.wallet?.is_frozen ? ' · wallet frozen' : ''}{user.self_exclusion ? ` · self-excluded until ${formatDateTime(user.self_exclusion.ends_at)}` : ''}
        </p>

        {user.referred_by && (
          <Link to={`/admin/affiliate/partners/${user.referred_by.partner_id}`}
            className="flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs text-blue-100 hover:bg-blue-500/20">
            <Handshake className="h-4 w-4" />
            Referred by partner <b>{user.referred_by.partner_code}</b>
            {user.referred_by.registered_at && <span className="text-blue-200/70">· {formatDateTime(user.referred_by.registered_at)}</span>}
            <span className="ml-auto">Open partner →</span>
          </Link>
        )}

        <div className="space-y-2">
          <h4 className="text-sm font-bold text-white">Latest bets</h4>
          {entries.length === 0 ? <p className="text-xs text-slate-500">No bets yet.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-xs">
                <thead className="text-[10px] uppercase text-slate-500">
                  <tr><th className="py-1.5">Time</th><th>Game</th><th>Round</th><th className="text-right">Bet</th><th className="text-right">Won</th><th className="text-right">Status</th></tr>
                </thead>
                <tbody className="divide-y divide-dark-border/60 text-slate-200">
                  {entries.map((e) => (
                    <tr key={e.entry_id}>
                      <td className="py-1.5">{formatDateTime(e.created_at)}</td>
                      <td>{GAME_NAMES[e.game_id || ''] || e.game_id || '—'}</td>
                      <td>{e.round_no ?? '—'}</td>
                      <td className="text-right">{formatPaiseToRupee(e.bet_amount, false)}</td>
                      <td className={`text-right ${e.payout_amount > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>{formatPaiseToRupee(e.payout_amount, false)}</td>
                      <td className="text-right">{e.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="space-y-3 pt-3 border-t border-dark-border">
          <h4 className="text-sm font-bold text-white">Administrative Actions</h4>
          <Link to={`/admin/wallet-adjustment?user=${encodeURIComponent(user.phone ? user.phone.slice(3) : user.username)}`}>
            <Button variant="secondary" size="sm" leftIcon={<Coins className="w-4 h-4" />}>Manual Wallet Adjustment</Button>
          </Link>
        </div>
      </div>
    </div>
  )
}

const Stat: React.FC<{ label: string; value: string; tone?: string; small?: boolean }> = ({ label, value, tone = 'text-white', small }) => (
  <div className="p-3.5 rounded-xl bg-dark-elevated border border-dark-border text-center">
    <span className="text-xs text-slate-400 block mb-1">{label}</span>
    <span className={`${small ? 'text-xs' : 'text-base'} font-black font-mono ${tone}`}>{value}</span>
  </div>
)
