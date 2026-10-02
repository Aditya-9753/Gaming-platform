import React from 'react'
import { Info, Wallet } from 'lucide-react'

export const WalletCard: React.FC = () => (
  <section className="rounded-2xl border border-dark-border bg-dark-card p-6 shadow-xl space-y-3">
    <div className="flex items-center gap-2 text-white">
      <Wallet className="h-5 w-5 text-emerald-400" />
      <h3 className="font-bold">Platform credits</h3>
    </div>
    <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-slate-300">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
      <p>Deposits and withdrawals are not enabled by the backend yet. No payment or balance changes are simulated here.</p>
    </div>
  </section>
)
