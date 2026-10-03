import React, { useEffect, useState } from 'react'
import { BalanceCard } from '../../components/wallet/BalanceCard'
import { WalletCard } from '../../components/wallet/WalletCard'
import { DailyClaimCard } from '../../components/wallet/DailyClaimCard'
import { TransactionList } from '../../components/wallet/TransactionList'
import { useWalletStore } from '../../store/wallet.store'
import { Link } from 'react-router-dom'
import { Wallet as WalletIcon, History, ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import type { WalletTransaction } from '../../types/wallet.types'
import { walletApi } from '../../services/wallet.api'

export const WalletPage: React.FC = () => {
  const { balance } = useWalletStore()
  const [activeTab, setActiveTab] = useState<'overview' | 'history'>('overview')
  const [transactions, setTransactions] = useState<WalletTransaction[]>([])
  const [historyError, setHistoryError] = useState(false)
  const [balanceError, setBalanceError] = useState(false)

  useEffect(() => {
    walletApi.getBalance().then((value) => useWalletStore.getState().setBalance(value)).catch(() => setBalanceError(true))
    walletApi.getTransactions().then((value) => setTransactions(value.items)).catch(() => setHistoryError(true))
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <WalletIcon className="w-6 h-6 text-emerald-400" />
        <div>
          <h2 className="text-2xl font-black text-white">My Wallet</h2>
          <p className="text-xs text-slate-400">View your server-backed platform credit balance and ledger</p>
        </div>
      </div>

      {/* Balance Summary */}
      {balanceError ? <p className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-sm text-rose-300">Wallet balance could not be loaded.</p> : <BalanceCard balance={balance} />}

      <div className="grid grid-cols-2 gap-3">
        <Link to="/payments?tab=deposit" className="flex items-center justify-center gap-2 rounded-xl bg-emerald-500 py-3 text-sm font-black text-dark-bg hover:brightness-110">
          <ArrowDownLeft className="h-4 w-4" />Deposit
        </Link>
        <Link to="/payments?tab=withdraw" className="flex items-center justify-center gap-2 rounded-xl border border-dark-border bg-dark-card py-3 text-sm font-black text-white hover:border-slate-500">
          <ArrowUpRight className="h-4 w-4" />Withdraw
        </Link>
      </div>

      {/* Daily Claim */}
      <DailyClaimCard />

      {/* Tabs */}
      <div className="grid grid-cols-2 gap-2 p-1 bg-dark-elevated rounded-xl">
        <button
          onClick={() => setActiveTab('overview')}
          className={`py-2.5 rounded-lg text-sm font-bold transition-all ${
            activeTab === 'overview'
              ? 'bg-emerald-500 text-dark-bg shadow'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Wallet information
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold transition-all ${
            activeTab === 'history'
              ? 'bg-emerald-500 text-dark-bg shadow'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <History className="w-4 h-4" />
          <span>Transaction History</span>
        </button>
      </div>

      {activeTab === 'overview' ? (
        <WalletCard />
      ) : (
        <div className="bg-dark-card border border-dark-border rounded-2xl overflow-hidden shadow-xl">
          <div className="p-4 border-b border-dark-border">
            <h4 className="text-sm font-bold text-white">Recent Transactions</h4>
          </div>
          {historyError ? <p className="p-5 text-sm text-rose-300">Transaction history could not be loaded.</p> : <TransactionList transactions={transactions} />}
        </div>
      )}
    </div>
  )
}
