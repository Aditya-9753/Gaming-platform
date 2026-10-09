import React from 'react'
import { Wallet, ShieldCheck, ArrowUpRight, ArrowDownLeft } from 'lucide-react'
import type { WalletBalance } from '../../types/wallet.types'
import { formatPaiseToRupee } from '../../utils/formatters'
import { t as tr } from '../../i18n'

export interface BalanceCardProps {
  balance: WalletBalance
  onDepositClick?: () => void
  onWithdrawClick?: () => void
}

export const BalanceCard: React.FC<BalanceCardProps> = ({
  balance,
  onDepositClick,
  onWithdrawClick,
}) => {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-950/40 via-dark-card to-dark-card border border-emerald-500/20 p-6 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider mb-1">
            <Wallet className="w-4 h-4" />
            <span>{tr('Total Available Balance')}</span>
          </div>
          <div className="text-3xl sm:text-4xl font-black font-mono text-white tracking-tight">
            {formatPaiseToRupee(balance.realBalancePaise)}
          </div>
          <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
            <span>Bonus: {formatPaiseToRupee(balance.bonusBalancePaise)}</span>
            <span>•</span>
            <span className="flex items-center gap-1 text-slate-500">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>{tr('INR Secured')}</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {onDepositClick && (
            <button
              onClick={onDepositClick}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-bg text-xs font-black transition-all shadow-md"
            >
              <ArrowDownLeft className="w-4 h-4" />
              <span>{tr('Deposit')}</span>
            </button>
          )}
          {onWithdrawClick && (
            <button
              onClick={onWithdrawClick}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-dark-elevated hover:bg-slate-700 text-white text-xs font-bold border border-dark-border transition-all"
            >
              <ArrowUpRight className="w-4 h-4" />
              <span>{tr('Withdraw')}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

