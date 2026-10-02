import React, { useState } from 'react'
import { ShieldCheck, CheckCircle2, XCircle } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { apiClient } from '../../services/api'
import { showToast } from '../../components/common/Toast'

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

export const FairnessPage: React.FC = () => {
  const [roundId, setRoundId] = useState('')
  const [result, setResult] = useState<Verification | null>(null)
  const [loading, setLoading] = useState(false)

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!roundId.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const { data } = await apiClient.get<Verification>(`/rounds/${encodeURIComponent(roundId.trim())}/verify`)
      setResult(data)
    } catch {
      showToast({ title: 'Verification unavailable', message: 'This round may not be settled yet, or its ID is invalid.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const verified = result?.hash_valid && result.result_matches

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-500/20 bg-cyan-500/10 text-cyan-400"><ShieldCheck className="h-7 w-7" /></div>
        <div><h2 className="text-2xl font-black text-white">Provably Fair Verification</h2><p className="text-xs text-slate-400">Verify settled game rounds using the backend fairness module</p></div>
      </div>
      <div className="rounded-2xl border border-cyan-500/20 bg-dark-card p-5 text-sm text-slate-300">
        The server publishes the seed commitment before a round opens. Once settled, the server reveals the seed and independently recomputes the outcome. Enter the round ID below to request that verification; active round seeds are never disclosed.
      </div>
      <form onSubmit={handleVerify} className="space-y-4 rounded-2xl border border-dark-border bg-dark-card p-6">
        <Input label="Settled round ID" value={roundId} onChange={(event) => setRoundId(event.target.value)} required placeholder="Paste the round ID" />
        <Button type="submit" isLoading={loading} disabled={!roundId.trim()} className="w-full">Verify round with server</Button>
      </form>
      {result && (
        <section className={`space-y-4 rounded-2xl border p-5 ${verified ? 'border-emerald-500/30 bg-emerald-950/20' : 'border-rose-500/30 bg-rose-950/20'}`}>
          <div className="flex items-center gap-2 text-white">{verified ? <CheckCircle2 className="h-5 w-5 text-emerald-400" /> : <XCircle className="h-5 w-5 text-rose-400" />}<h3 className="font-bold">{verified ? 'Round verified' : 'Verification mismatch'}</h3></div>
          <dl className="grid gap-3 text-xs sm:grid-cols-2">
            <div><dt className="text-slate-400">Game / round</dt><dd className="mt-1 text-white">{result.game_id} / #{result.round_no}</dd></div>
            <div><dt className="text-slate-400">Nonce</dt><dd className="mt-1 text-white">{result.nonce}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Server seed hash</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.server_seed_hash}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Revealed server seed</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.server_seed}</dd></div>
            <div className="sm:col-span-2"><dt className="text-slate-400">Client seed</dt><dd className="mt-1 break-all font-mono text-slate-200">{result.client_seed}</dd></div>
            <div><dt className="text-slate-400">Stored result</dt><dd className="mt-1 break-all font-mono text-slate-200">{JSON.stringify(result.stored_result)}</dd></div>
            <div><dt className="text-slate-400">Recomputed result</dt><dd className="mt-1 break-all font-mono text-slate-200">{JSON.stringify(result.recomputed_result)}</dd></div>
          </dl>
        </section>
      )}
    </div>
  )
}
