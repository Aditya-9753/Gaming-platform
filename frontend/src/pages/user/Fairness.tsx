import React, { useEffect, useState } from 'react'
import { CheckCircle2, Cpu, Server, ShieldCheck, XCircle } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { apiClient } from '../../services/api'
import { showToast } from '../../components/common/Toast'
import { verifyManually, type ManualVerification } from '../../utils/provablyFair'

interface Verification {
  round_id: string
  game_id: string
  round_no: number
  server_seed_hash: string
  server_seed: string
  client_seed: string
  nonce: number
  stored_result: Record<string, unknown>
  recomputed_result: Record<string, unknown>
  hash_valid: boolean
  result_matches: boolean
}

interface RecentRound {
  round_id: string
  round_no: number
  server_seed: string | null
  server_seed_hash: string
  client_seed: string | null
  result: Record<string, unknown> | null
}

type Game = 'wingo' | 'aviator'
const GAMES: Array<{ id: string; label: string; kind: Game }> = [
  { id: 'wingo_30s', label: 'WinGo 30s', kind: 'wingo' },
  { id: 'wingo_1m', label: 'WinGo 1m', kind: 'wingo' },
  { id: 'wingo_3m', label: 'WinGo 3m', kind: 'wingo' },
  { id: 'wingo_5m', label: 'WinGo 5m', kind: 'wingo' },
  { id: 'aviator', label: 'Aviator', kind: 'aviator' },
]

const outcomeOf = (r: RecentRound): string => {
  const res = r.result ?? {}
  if (typeof res.number === 'number') return `No. ${res.number}`
  if (res.crash_point !== undefined) return `${Number(res.crash_point).toFixed(2)}x`
  return '—'
}

export const FairnessPage: React.FC = () => {
  const [gameId, setGameId] = useState('wingo_30s')
  const [recent, setRecent] = useState<RecentRound[]>([])
  const [roundId, setRoundId] = useState('')
  const [result, setResult] = useState<Verification | null>(null)
  const [loading, setLoading] = useState(false)
  // manual (in-browser) verification
  const [mGame, setMGame] = useState<Game>('wingo')
  const [serverSeed, setServerSeed] = useState('')
  const [seedHash, setSeedHash] = useState('')
  const [clientSeed, setClientSeed] = useState('')
  const [nonce, setNonce] = useState('')
  const [edge, setEdge] = useState('300')
  const [formula, setFormula] = useState('2')
  const [manual, setManual] = useState<ManualVerification | null>(null)

  useEffect(() => {
    apiClient.get<RecentRound[]>(`/games/${gameId}/history`, { params: { limit: 10 } })
      .then(({ data }) => setRecent(data))
      .catch(() => setRecent([]))
  }, [gameId])

  const verifyOnServer = async (id: string) => {
    if (!id.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const { data } = await apiClient.get<Verification>(`/rounds/${encodeURIComponent(id.trim())}/verify`)
      setResult(data)
    } catch {
      showToast({ title: 'Verification unavailable', message: 'This round may not be settled yet, or its ID is invalid.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const fillManual = (r: RecentRound) => {
    const kind = GAMES.find((g) => g.id === gameId)?.kind ?? 'wingo'
    setMGame(kind)
    setServerSeed(r.server_seed ?? '')
    setSeedHash(r.server_seed_hash)
    setClientSeed(r.client_seed ?? r.round_id)
    setNonce(String(r.round_no))
    const bp = (r.result ?? {}).house_edge_bp
    if (typeof bp === 'number') setEdge(String(bp))
    const f = (r.result ?? {}).crash_formula
    setFormula(typeof f === 'number' ? String(f) : '1') // rounds from before versioning used formula 1
    setManual(null)
    document.getElementById('manual-verify')?.scrollIntoView({ behavior: 'smooth' })
  }

  const runManual = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      setManual(await verifyManually({ game: mGame, serverSeed, serverSeedHash: seedHash, clientSeed, nonce: Number(nonce), houseEdgeBp: Number(edge), crashFormula: Number(formula) }))
    } catch {
      showToast({ title: 'Could not compute', message: 'Your browser blocked WebCrypto (open the site over https).', type: 'error' })
    }
  }

  const verified = result?.hash_valid && result.result_matches

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-500/20 bg-cyan-500/10 text-cyan-400"><ShieldCheck className="h-7 w-7" /></div>
        <div><h2 className="text-2xl font-black text-white">Provably Fair</h2><p className="text-xs text-slate-400">Check for yourself that every result was fixed before anyone could bet</p></div>
      </div>

      <ol className="grid gap-3 text-xs text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['1. Commit', 'Before a round opens the server creates a secret server seed and publishes only its SHA-256 hash.'],
          ['2. Bet', 'You bet knowing the commitment, the public client seed and the round number (nonce).'],
          ['3. Draw', 'Result = HMAC-SHA256(serverSeed, "clientSeed:nonce") → WinGo: number 0-9, Aviator: crash point.'],
          ['4. Reveal', 'After the round the seed is revealed. Hash it — it must equal the commitment — and recompute the result.'],
        ].map(([t, d]) => (
          <li key={t} className="rounded-2xl border border-dark-border bg-dark-card p-4"><p className="font-black text-cyan-300">{t}</p><p className="mt-1 text-slate-400">{d}</p></li>
        ))}
      </ol>
      <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-200">No one — including the platform's super admin — can see a seed or change a result while a round is running. There is no admin setting, endpoint or "test mode" that reads or overrides outcomes.</p>

      {/* Recent rounds */}
      <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-black text-white">Recent settled rounds</h3>
          <div className="flex flex-wrap gap-1.5">
            {GAMES.map((g) => (
              <button key={g.id} type="button" onClick={() => setGameId(g.id)} className={`rounded-full px-3 py-1 text-xs font-bold ${gameId === g.id ? 'bg-cyan-500 text-dark-bg' : 'bg-dark-elevated text-slate-400'}`}>{g.label}</button>
            ))}
          </div>
        </div>
        {recent.length === 0 ? <p className="text-xs text-slate-400">No settled rounds yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-xs">
              <thead><tr className="text-left text-slate-400"><th className="py-1.5">Round</th><th className="py-1.5">Result</th><th className="py-1.5">Commitment (hash)</th><th className="py-1.5 text-right">Verify</th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.round_id} className="border-t border-dark-border/50">
                    <td className="py-2 font-mono text-white">#{r.round_no}</td>
                    <td className="py-2 font-bold text-cyan-300">{outcomeOf(r)}</td>
                    <td className="py-2 font-mono text-slate-500">{r.server_seed_hash.slice(0, 18)}…</td>
                    <td className="py-2 text-right">
                      <div className="flex justify-end gap-1.5">
                        <button type="button" onClick={() => { setRoundId(r.round_id); void verifyOnServer(r.round_id) }} className="flex items-center gap-1 rounded-lg bg-dark-elevated px-2 py-1 text-slate-300 hover:text-white"><Server className="h-3 w-3" />Server</button>
                        <button type="button" onClick={() => fillManual(r)} className="flex items-center gap-1 rounded-lg bg-cyan-500/15 px-2 py-1 font-bold text-cyan-300"><Cpu className="h-3 w-3" />My browser</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Server verification */}
      <form onSubmit={(e) => { e.preventDefault(); void verifyOnServer(roundId) }} className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-5">
        <h3 className="font-black text-white">Verify a round by ID</h3>
        <Input label="Settled round ID" value={roundId} onChange={(event) => setRoundId(event.target.value)} required placeholder="Paste the round ID" />
        <Button type="submit" isLoading={loading} disabled={!roundId.trim()} className="w-full">Verify with server</Button>
      </form>
      {result && (
        <section className={`space-y-4 rounded-2xl border p-5 ${verified ? 'border-emerald-500/30 bg-emerald-950/20' : 'border-rose-500/30 bg-rose-950/20'}`}>
          <div className="flex items-center gap-2 text-white">{verified ? <CheckCircle2 className="h-5 w-5 text-emerald-400" /> : <XCircle className="h-5 w-5 text-rose-400" />}<h3 className="font-bold">{verified ? 'Round verified' : 'Verification mismatch'}</h3></div>
          <dl className="grid gap-3 text-xs sm:grid-cols-2">
            <div><dt className="text-slate-400">Game / round</dt><dd className="mt-1 text-white">{result.game_id} / #{result.round_no}</dd></div>
            <div><dt className="text-slate-400">Nonce</dt><dd className="mt-1 text-white">{result.nonce}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Server seed hash (commitment)</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.server_seed_hash}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Revealed server seed</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.server_seed}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Client seed</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.client_seed}</dd></div>
            <div><dt className="text-slate-400">Stored result</dt><dd className="mt-1 break-all font-mono text-slate-200">{JSON.stringify(result.stored_result)}</dd></div>
            <div><dt className="text-slate-400">Recomputed result</dt><dd className="mt-1 break-all font-mono text-slate-200">{JSON.stringify(result.recomputed_result)}</dd></div>
          </dl>
        </section>
      )}

      {/* In-browser verification */}
      <form id="manual-verify" onSubmit={(e) => void runManual(e)} className="space-y-4 rounded-2xl border border-cyan-500/20 bg-dark-card p-5">
        <div>
          <h3 className="flex items-center gap-2 font-black text-white"><Cpu className="h-4 w-4 text-cyan-400" />Verify in your browser (no server involved)</h3>
          <p className="text-xs text-slate-400">Paste the revealed seed, the commitment hash, the client seed and the nonce. Everything is computed locally with your browser's WebCrypto.</p>
        </div>
        <div className="flex gap-2">
          {(['wingo', 'aviator'] as const).map((g) => (
            <button key={g} type="button" onClick={() => setMGame(g)} className={`rounded-full px-3 py-1 text-xs font-bold ${mGame === g ? 'bg-cyan-500 text-dark-bg' : 'bg-dark-elevated text-slate-400'}`}>{g === 'wingo' ? 'WinGo' : 'Aviator'}</button>
          ))}
        </div>
        <Input label="Server seed (revealed after the round)" value={serverSeed} onChange={(e) => setServerSeed(e.target.value)} required spellCheck={false} />
        <Input label="Server seed hash (published before the round)" value={seedHash} onChange={(e) => setSeedHash(e.target.value)} required spellCheck={false} />
        <div className="grid gap-3 sm:grid-cols-3">
          <Input label="Client seed" value={clientSeed} onChange={(e) => setClientSeed(e.target.value)} required spellCheck={false} />
          <Input label="Nonce (round number)" type="number" value={nonce} onChange={(e) => setNonce(e.target.value)} required />
          {mGame === 'aviator' && <Input label="House edge (bp)" type="number" value={edge} onChange={(e) => setEdge(e.target.value)} />}
          {mGame === 'aviator' && (
            <label className="block space-y-1.5 text-left">
              <span className="block text-xs font-semibold text-slate-300">Crash formula</span>
              <select value={formula} onChange={(e) => setFormula(e.target.value)} className="w-full rounded-xl border border-dark-border bg-dark-card px-3.5 py-2.5 text-sm text-white">
                <option value="2">v2 — current (edge applied once)</option>
                <option value="1">v1 — rounds before the fix</option>
              </select>
            </label>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={!serverSeed || !seedHash || !clientSeed || nonce === ''}>Check fairness</Button>

        {manual && (
          <div className={`space-y-2 rounded-xl border p-4 text-xs ${manual.hashMatches ? 'border-emerald-500/30 bg-emerald-950/20' : 'border-rose-500/30 bg-rose-950/20'}`}>
            <p className="flex items-center gap-2 text-sm font-bold text-white">
              {manual.hashMatches ? <CheckCircle2 className="h-5 w-5 text-emerald-400" /> : <XCircle className="h-5 w-5 text-rose-400" />}
              {manual.hashMatches ? 'Seed matches the commitment — the result was fixed before betting' : 'Seed does NOT match the commitment'}
            </p>
            <p className="text-slate-300">Result from these seeds: <b className="text-white">{manual.outcome}</b> {Object.entries(manual.details).map(([k, v]) => <span key={k} className="ml-2 font-mono text-slate-400">{k}={String(v)}</span>)}</p>
            <p className="break-all font-mono text-slate-500">SHA-256(seed) = {manual.computedHash}</p>
            <p className="font-mono text-slate-500">random float = {manual.float}</p>
          </div>
        )}
      </form>
    </div>
  )
}
