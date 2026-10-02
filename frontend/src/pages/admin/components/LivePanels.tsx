import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink, X } from 'lucide-react'
import { apiClient } from '../../../services/api'
import { formatPaiseToRupee } from '../../../utils/formatters'

export const GAME_LABEL: Record<string, string> = {
  aviator: 'Aviator', mines: 'Mines', cricket: 'Cricket', color: 'Color (old)',
  wingo_30s: 'WinGo 30s', wingo_1m: 'WinGo 1m', wingo_3m: 'WinGo 3m', wingo_5m: 'WinGo 5m',
}

export type PanelTarget =
  | { type: 'game'; id: string }
  | { type: 'list'; kind: string; hour?: number }
  | { type: 'bet'; id: string }

export interface BetRow {
  id: string; user_id: string; username: string; game_id: string; round_id: string; round_no: number | null
  amount: number; pick: string; status: string; payout: number; multiplier: number | null; revealed?: number | null; at: string
}

export const ago = (iso: string | null | undefined, now: number) => {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export const countdown = (iso: string | undefined, now: number) => {
  if (!iso) return null
  const s = Math.max(0, Math.ceil((Date.parse(iso) - now) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const money = (paise: number) => formatPaiseToRupee(paise)
export const signed = (paise: number) => `${paise >= 0 ? '+' : '−'}${formatPaiseToRupee(Math.abs(paise))}`
export const statusTone: Record<string, string> = { WON: 'text-emerald-400', LOST: 'text-rose-400', PLACED: 'text-amber-300', REFUNDED: 'text-slate-300', CANCELLED: 'text-slate-400' }

export const PlayerLink: React.FC<{ id?: string | null; name?: string | null }> = ({ id, name }) =>
  id ? (
    <Link to={`/admin/users/${id}`} onClick={(e) => e.stopPropagation()} className="font-bold text-white underline-offset-2 hover:text-emerald-300 hover:underline">{name ?? '—'}</Link>
  ) : <span className="font-bold text-white">{name ?? '—'}</span>

export const betResult = (b: Pick<BetRow, 'status' | 'payout' | 'multiplier'>) =>
  b.status === 'WON' ? `+${money(b.payout)}${b.multiplier ? ` (${b.multiplier.toFixed(2)}x)` : ''}` : b.status === 'PLACED' ? 'In play' : b.status

/** Polls a URL while mounted and the tab is visible. */
function usePoll<T>(url: string, params: Record<string, unknown>, ms: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState(false)
  const key = JSON.stringify(params)
  const inflight = useRef(false)
  const load = useCallback(async () => {
    if (inflight.current) return
    inflight.current = true
    try {
      const { data: body } = await apiClient.get<T>(url, { params: JSON.parse(key) })
      setData(body)
      setError(false)
    } catch {
      setError(true)
    } finally {
      inflight.current = false
    }
  }, [url, key])
  useEffect(() => {
    setData(null)
    void load()
    const t = setInterval(() => { if (document.visibilityState === 'visible') void load() }, ms)
    return () => clearInterval(t)
  }, [load, ms])
  return { data, error }
}

const Section: React.FC<{ title: string; children: React.ReactNode; right?: React.ReactNode }> = ({ title, children, right }) => (
  <section className="space-y-2">
    <div className="flex items-center justify-between"><h3 className="text-xs font-black uppercase tracking-wider text-slate-400">{title}</h3>{right}</div>
    {children}
  </section>
)

const Empty: React.FC<{ text: string }> = ({ text }) => <p className="rounded-lg bg-dark-elevated/40 p-3 text-xs text-slate-400">{text}</p>

export const BetsTable: React.FC<{ rows: BetRow[]; now: number; onBet: (id: string) => void; showGame?: boolean }> = ({ rows, now, onBet, showGame = true }) =>
  rows.length === 0 ? <Empty text="No bets." /> : (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="text-left text-slate-400"><th className="py-1.5">Player</th>{showGame && <th className="py-1.5">Game</th>}<th className="py-1.5">Pick</th><th className="py-1.5 text-right">Bet</th><th className="py-1.5 text-right">Result</th><th className="py-1.5 text-right">When</th></tr></thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id} onClick={() => onBet(b.id)} className="cursor-pointer border-t border-dark-border/50 hover:bg-dark-elevated/60">
              <td className="py-1.5"><PlayerLink id={b.user_id} name={b.username} /></td>
              {showGame && <td className="py-1.5 text-slate-300">{GAME_LABEL[b.game_id] ?? b.game_id}{b.round_no ? <span className="text-slate-500"> #{b.round_no}</span> : null}</td>}
              <td className="py-1.5 text-slate-400">{b.pick}{b.revealed ? ` · ${b.revealed} gems` : ''}</td>
              <td className="py-1.5 text-right font-mono">{money(b.amount)}</td>
              <td className={`py-1.5 text-right font-bold ${statusTone[b.status] ?? 'text-slate-300'}`}>{betResult(b)}</td>
              <td className="py-1.5 text-right text-slate-500">{ago(b.at, now)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

// ---------------------------------------------------------------- game
interface LiveRound { kind: string; round_id?: string; round_no?: number; status?: string; open_bets: number; open_stake: number; period?: string; betting_closes_at?: string; result_at?: string; multiplier?: number; outcome?: string | null; live_matches?: number }
interface RoundRow { round_id: string; round_no: number; status: string; outcome: string | null; bets: number; wagered: number; paid: number; house_net: number; ended_at: string | null }
interface GameDetail {
  name: string; is_active: boolean; current?: LiveRound | null; live_bets?: BetRow[]; recent_rounds?: RoundRow[]; today_bets?: BetRow[]
  matches?: { match_id: string; teams: string; status: string; score: string | null; winner: string | null; predictions: number; staked: number; open: number }[]
  predictions?: { id: string; user_id: string; username: string; match: string; pick: string; amount: number; odds: number | null; status: string; payout: number; at: string }[]
}

export const LiveStatus: React.FC<{ live?: LiveRound | null; now: number; gameId: string }> = ({ live, now, gameId }) => {
  if (!live) return <span className="text-slate-500">No round yet</span>
  if (live.kind === 'sessions') return <span>{live.open_bets} open session{live.open_bets === 1 ? '' : 's'}</span>
  if (live.kind === 'matches') return <span>{live.live_matches ?? 0} live match{live.live_matches === 1 ? '' : 'es'} · {live.open_bets} open predictions</span>
  const st = (live.status ?? '').toUpperCase()
  if (gameId === 'aviator') {
    if (st === 'RUNNING') return <span className="font-mono font-black text-emerald-300">✈ {live.multiplier?.toFixed(2) ?? '1.00'}x flying</span>
    if (st === 'BETTING_OPEN') return <span className="text-amber-300">Taking bets · {countdown(live.betting_closes_at, now)}</span>
    if (live.outcome) return <span className="text-rose-300">Flew away at {live.outcome}</span>
  }
  if (live.result_at && !live.outcome) {
    const closed = live.betting_closes_at && Date.parse(live.betting_closes_at) <= now
    return <span className={closed ? 'text-rose-300' : 'text-amber-300'}>{closed ? 'Betting closed' : 'Taking bets'} · draw in {countdown(live.result_at, now)}</span>
  }
  if (live.outcome) return <span>Last result {live.outcome}</span>
  return <span className="text-slate-400">{live.status?.toLowerCase().replace(/_/g, ' ')}</span>
}

const GamePanel: React.FC<{ id: string; includeBots: boolean; now: number; onBet: (id: string) => void }> = ({ id, includeBots, now, onBet }) => {
  const { data, error } = usePoll<GameDetail>(`/admin/dashboard/live/games/${id}`, { include_bots: includeBots }, 2000)
  if (!data) return <Empty text={error ? 'Could not load this game.' : 'Loading…'} />
  if (data.matches) {
    return (
      <div className="space-y-6">
        <Section title="Matches">
          {data.matches.length === 0 ? <Empty text="No matches loaded." /> : data.matches.map((m) => (
            <div key={m.match_id} className="rounded-xl border border-dark-border bg-dark-elevated/40 p-3 text-xs">
              <div className="flex justify-between gap-2"><b className="text-white">{m.teams}</b><span className={/live|progress/i.test(m.status) ? 'text-emerald-400' : 'text-slate-400'}>{m.status}</span></div>
              {m.score && <p className="mt-1 font-mono text-slate-300">{m.score}</p>}
              <p className="mt-1 text-slate-400">{m.predictions} predictions · {money(m.staked)} staked · {m.open} open{m.winner ? ` · winner ${m.winner}` : ''}</p>
            </div>
          ))}
        </Section>
        <Section title="Latest predictions">
          {(data.predictions ?? []).length === 0 ? <Empty text="No predictions from players yet." /> : (
            <table className="w-full text-xs"><tbody>
              {data.predictions!.map((p) => (
                <tr key={p.id} className="border-t border-dark-border/50">
                  <td className="py-1.5"><PlayerLink id={p.user_id} name={p.username} /><p className="text-slate-500">{p.match}</p></td>
                  <td className="py-1.5 text-slate-300">{p.pick}{p.odds ? ` @ ${p.odds.toFixed(2)}` : ''}</td>
                  <td className="py-1.5 text-right font-mono">{money(p.amount)}</td>
                  <td className={`py-1.5 text-right font-bold ${statusTone[p.status] ?? 'text-slate-300'}`}>{p.status === 'WON' ? `+${money(p.payout)}` : p.status}</td>
                  <td className="py-1.5 text-right text-slate-500">{ago(p.at, now)}</td>
                </tr>
              ))}
            </tbody></table>
          )}
        </Section>
      </div>
    )
  }
  const cur = data.current
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="col-span-2 rounded-xl border border-dark-border bg-dark-elevated/40 p-3">
          <p className="text-slate-400">{id === 'mines' ? 'Right now' : `Round #${cur?.round_no ?? '—'}${cur?.period ? ` · period ${cur.period}` : ''}`}</p>
          <p className="mt-1 text-base font-black text-white"><LiveStatus live={cur} now={now} gameId={id} /></p>
        </div>
        <div className="rounded-xl border border-dark-border bg-dark-elevated/40 p-3"><p className="text-slate-400">Bets in play</p><p className="font-mono text-lg font-black text-white">{cur?.open_bets ?? 0}</p></div>
        <div className="rounded-xl border border-dark-border bg-dark-elevated/40 p-3"><p className="text-slate-400">Stake in play</p><p className="font-mono text-lg font-black text-white">{money(cur?.open_stake ?? 0)}</p></div>
      </div>
      <Section title={id === 'mines' ? 'Open sessions' : 'Bets in this round'}>
        <BetsTable rows={data.live_bets ?? []} now={now} onBet={onBet} showGame={false} />
      </Section>
      {id !== 'mines' && (
        <Section title="Recent results">
          {(data.recent_rounds ?? []).length === 0 ? <Empty text="No finished rounds yet." /> : (
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400"><th className="py-1.5">Round</th><th className="py-1.5">Result</th><th className="py-1.5 text-right">Bets</th><th className="py-1.5 text-right">Wagered</th><th className="py-1.5 text-right">House</th></tr></thead>
              <tbody>
                {data.recent_rounds!.map((r) => (
                  <tr key={r.round_id} className="border-t border-dark-border/50">
                    <td className="py-1.5 font-mono text-slate-300">#{r.round_no}</td>
                    <td className="py-1.5 font-bold text-white">{r.outcome ?? r.status.toLowerCase()}</td>
                    <td className="py-1.5 text-right">{r.bets}</td>
                    <td className="py-1.5 text-right font-mono">{money(r.wagered)}</td>
                    <td className={`py-1.5 text-right font-mono font-bold ${r.house_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{signed(r.house_net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}
      <Section title="Today's bets"><BetsTable rows={data.today_bets ?? []} now={now} onBet={onBet} showGame={false} /></Section>
    </div>
  )
}

// ---------------------------------------------------------------- list
interface PlayerRow { user_id: string; username: string; is_active: boolean; joined_at: string | null; last_login_at: string | null; balance: number; locked: number; bets_today: number; wagered_today: number }
interface TicketRow { id: string; user_id: string | null; username: string | null; subject: string; status: string; priority: string; at: string | null }
interface ListData { title: string; shape: 'players' | 'bets' | 'tickets'; rows: (PlayerRow | BetRow | TicketRow)[] }

const ListPanel: React.FC<{ kind: string; hour?: number; includeBots: boolean; now: number; onBet: (id: string) => void; onTitle: (t: string) => void }> = ({ kind, hour, includeBots, now, onBet, onTitle }) => {
  const { data, error } = usePoll<ListData>(`/admin/dashboard/live/drilldown/${kind}`, { include_bots: includeBots, ...(hour !== undefined ? { hour } : {}) }, 5000)
  useEffect(() => { if (data) onTitle(data.title) }, [data, onTitle])
  if (!data) return <Empty text={error ? 'Could not load this list.' : 'Loading…'} />
  const count = <span className="text-xs text-slate-500">{data.rows.length}{data.rows.length >= 200 ? '+' : ''} rows</span>
  if (data.shape === 'bets') return <Section title="Bets" right={count}><BetsTable rows={data.rows as BetRow[]} now={now} onBet={onBet} /></Section>
  if (data.shape === 'tickets') {
    const rows = data.rows as TicketRow[]
    return (
      <Section title="Tickets" right={<Link to="/admin/support" className="flex items-center gap-1 text-xs text-emerald-300 hover:underline">Open support <ExternalLink className="h-3 w-3" /></Link>}>
        {rows.length === 0 ? <Empty text="No open tickets." /> : rows.map((t) => (
          <Link key={t.id} to="/admin/support" className="block rounded-xl border border-dark-border bg-dark-elevated/40 p-3 text-xs hover:border-emerald-500/50">
            <div className="flex justify-between gap-2"><b className="text-white">{t.subject}</b><span className="text-amber-300">{t.status}</span></div>
            <p className="mt-1 text-slate-400">{t.username ?? 'unknown'} · {t.priority.toLowerCase()} priority · {ago(t.at, now)}</p>
          </Link>
        ))}
      </Section>
    )
  }
  const rows = data.rows as PlayerRow[]
  return (
    <Section title="Players" right={count}>
      {rows.length === 0 ? <Empty text="Nobody here right now." /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-slate-400"><th className="py-1.5">Player</th><th className="py-1.5 text-right">Balance</th><th className="py-1.5 text-right">Bets today</th><th className="py-1.5 text-right">Wagered</th><th className="py-1.5 text-right">Last seen</th></tr></thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.user_id} className="border-t border-dark-border/50">
                  <td className="py-1.5"><PlayerLink id={p.user_id} name={p.username} />{!p.is_active && <span className="ml-1.5 rounded bg-rose-500/20 px-1 text-[10px] text-rose-300">suspended</span>}<p className="text-slate-500">joined {ago(p.joined_at, now)}</p></td>
                  <td className="py-1.5 text-right font-mono">{money(p.balance)}{p.locked > 0 && <p className="text-slate-500">{money(p.locked)} in play</p>}</td>
                  <td className="py-1.5 text-right">{p.bets_today}</td>
                  <td className="py-1.5 text-right font-mono">{money(p.wagered_today)}</td>
                  <td className="py-1.5 text-right text-slate-500">{ago(p.last_login_at, now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

// ---------------------------------------------------------------- bet
interface BetDetail extends BetRow {
  selection: Record<string, unknown>; updated_at: string | null
  round: { round_id: string; round_no: number; status: string; started_at: string | null; ended_at: string | null; server_seed_hash: string; client_seed: string; server_seed: string | null; outcome: string | null }
}

const Field: React.FC<{ k: string; children: React.ReactNode; mono?: boolean }> = ({ k, children, mono }) => (
  <div className="flex justify-between gap-4 border-t border-dark-border/50 py-1.5 text-xs first:border-0"><span className="shrink-0 text-slate-400">{k}</span><span className={`break-all text-right text-slate-200 ${mono ? 'font-mono' : ''}`}>{children}</span></div>
)

const BetPanel: React.FC<{ id: string; now: number }> = ({ id, now }) => {
  const { data, error } = usePoll<BetDetail>(`/admin/dashboard/live/bets/${id}`, {}, 3000)
  if (!data) return <Empty text={error ? 'Could not load this bet.' : 'Loading…'} />
  const r = data.round
  return (
    <div className="space-y-6">
      <Section title="Bet">
        <div className="rounded-xl border border-dark-border bg-dark-elevated/40 px-3 py-1">
          <Field k="Player"><PlayerLink id={data.user_id} name={data.username} /></Field>
          <Field k="Game">{GAME_LABEL[data.game_id] ?? data.game_id}</Field>
          <Field k="Pick">{data.pick}{data.revealed ? ` · ${data.revealed} gems opened` : ''}</Field>
          <Field k="Stake" mono>{money(data.amount)}</Field>
          <Field k="Result"><span className={`font-bold ${statusTone[data.status] ?? ''}`}>{betResult(data)}</span></Field>
          <Field k="Placed">{data.at ? new Date(data.at).toLocaleString() : '—'} ({ago(data.at, now)})</Field>
          <Field k="Bet id" mono>{data.id}</Field>
        </div>
      </Section>
      <Section title="Round">
        <div className="rounded-xl border border-dark-border bg-dark-elevated/40 px-3 py-1">
          <Field k="Round">#{r.round_no} · {r.status.toLowerCase()}</Field>
          <Field k="Outcome">{r.outcome ?? 'not drawn yet'}</Field>
          <Field k="Seed hash (committed)" mono>{r.server_seed_hash}</Field>
          <Field k="Client seed" mono>{r.client_seed}</Field>
          <Field k="Server seed" mono>{r.server_seed ?? 'hidden until the round finishes'}</Field>
        </div>
        {r.server_seed && <Link to="/fairness" className="inline-flex items-center gap-1 text-xs text-emerald-300 hover:underline">Verify on the fairness page <ExternalLink className="h-3 w-3" /></Link>}
      </Section>
    </div>
  )
}

// ---------------------------------------------------------------- drawer
export const LiveDrawer: React.FC<{ target: PanelTarget | null; includeBots: boolean; now: number; onClose: () => void; onOpen: (t: PanelTarget) => void; onBack?: () => void }> = ({ target, includeBots, now, onClose, onOpen, onBack }) => {
  const [listTitle, setListTitle] = useState('')
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!target) return null
  const openBet = (id: string) => onOpen({ type: 'bet', id })
  const title = target.type === 'game' ? GAME_LABEL[target.id] ?? target.id : target.type === 'bet' ? 'Bet details' : listTitle || 'Loading…'
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Close" className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-2xl flex-col border-l border-dark-border bg-dark-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-dark-border px-5 py-4">
          <div className="flex items-center gap-3">
            {onBack && <button type="button" onClick={onBack} aria-label="Back" className="rounded-lg p-1.5 text-slate-400 hover:bg-dark-elevated hover:text-white"><ArrowLeft className="h-5 w-5" /></button>}
            <div>
            <h2 className="text-lg font-black text-white">{title}</h2>
            <p className="flex items-center gap-1.5 text-[11px] text-slate-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />Live · updates automatically</p>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close panel" className="rounded-lg p-2 text-slate-400 hover:bg-dark-elevated hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {target.type === 'game' && <GamePanel key={target.id} id={target.id} includeBots={includeBots} now={now} onBet={openBet} />}
          {target.type === 'list' && <ListPanel key={`${target.kind}:${target.hour ?? ''}`} kind={target.kind} hour={target.hour} includeBots={includeBots} now={now} onBet={openBet} onTitle={setListTitle} />}
          {target.type === 'bet' && <BetPanel key={target.id} id={target.id} now={now} />}
        </div>
      </div>
    </div>
  )
}
