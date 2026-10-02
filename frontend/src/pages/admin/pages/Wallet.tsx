import React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../../components/common/Button'

export const WalletPage: React.FC = () => (
  <div className="space-y-6">
    <div>
      <h1 className="text-2xl font-black text-white">Wallet Operations</h1>
      <p className="text-xs text-slate-400">Wallet balances and audited adjustments for individual users.</p>
    </div>
    <section className="space-y-3 rounded-2xl border border-dark-border bg-dark-card p-6">
      <p className="text-sm text-slate-300">Platform treasury, payment gateway reserves, and withdrawal queues are not available from the current backend APIs. No estimates are shown here.</p>
      <div className="flex flex-wrap gap-3">
        <Link to="/admin/users"><Button variant="primary" size="sm">Find a user</Button></Link>
        <Link to="/admin/transactions"><Button variant="secondary" size="sm">Export transactions</Button></Link>
      </div>
    </section>
  </div>
)
