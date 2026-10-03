import React from 'react'
import { ArrowDownLeft, ArrowUpRight, Award, Gift, RefreshCw } from 'lucide-react'
import type { WalletTransaction } from '../../types/wallet.types'
import { formatPaiseToRupee, formatDateTime } from '../../utils/formatters'

export interface TransactionListProps {
  transactions: WalletTransaction[]
}

export const TransactionList: React.FC<TransactionListProps> = ({ transactions }) => {
  if (transactions.length === 0) {
    return (
      <div className="p-8 text-center text-xs text-slate-500">
        No transactions recorded yet
      </div>
    )
  }

  const typeConfig: Record<string, { icon: React.ReactNode; label: string; plus: boolean }> = {
    deposit: { icon: <ArrowDownLeft className="w-4 h-4 text-emerald-400" />, label: 'Deposit', plus: true },
    withdrawal: { icon: <ArrowUpRight className="w-4 h-4 text-rose-400" />, label: 'Withdrawal', plus: false },
    deposit_reversal: { icon: <ArrowUpRight className="w-4 h-4 text-rose-400" />, label: 'Deposit reversed', plus: false },
    withdrawal_hold: { icon: <ArrowUpRight className="w-4 h-4 text-amber-400" />, label: 'Withdrawal requested', plus: false },
    withdrawal_settle: { icon: <ArrowUpRight className="w-4 h-4 text-emerald-400" />, label: 'Withdrawal paid', plus: false },
    withdrawal_release: { icon: <ArrowDownLeft className="w-4 h-4 text-cyan-400" />, label: 'Withdrawal returned', plus: true },
    bet: { icon: <RefreshCw className="w-4 h-4 text-slate-400" />, label: 'Bet Placed', plus: false },
    win: { icon: <Award className="w-4 h-4 text-purple-400" />, label: 'Payout Won', plus: true },
    bonus: { icon: <Gift className="w-4 h-4 text-amber-400" />, label: 'Bonus Reward', plus: true },
    refund: { icon: <RefreshCw className="w-4 h-4 text-cyan-400" />, label: 'Refund', plus: true },
    adjustment: { icon: <RefreshCw className="w-4 h-4 text-slate-300" />, label: 'Admin Adjustment', plus: true },
    admin_adjustment: { icon: <RefreshCw className="w-4 h-4 text-slate-300" />, label: 'Admin Adjustment', plus: true },
  }

  return (
    <div className="divide-y divide-dark-border">
      {transactions.map((t) => {
        const conf = typeConfig[t.type] || {
          icon: <RefreshCw className="w-4 h-4 text-slate-400" />,
          label: t.type,
          plus: false,
        }
        return (
          <div
            key={t.id}
            className="flex items-center justify-between p-4 hover:bg-dark-elevated/40 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-dark-elevated border border-dark-border flex items-center justify-center">
                {conf.icon}
              </div>
              <div className="text-left">
                <span className="text-xs font-bold text-white block">
                  {t.description || conf.label}
                </span>
                <span className="text-[10px] text-slate-500">
                  {formatDateTime(t.createdAt)}
                </span>
              </div>
            </div>

            <div className="text-right">
              <span
                className={`text-xs font-black font-mono block ${
                  conf.plus ? 'text-emerald-400' : 'text-slate-300'
                }`}
              >
                {conf.plus ? '+' : '-'}
                {formatPaiseToRupee(t.amountPaise)}
              </span>
              <span
                className={`text-[10px] font-semibold uppercase ${
                  t.status === 'completed'
                    ? 'text-emerald-400'
                    : t.status === 'pending'
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }`}
              >
                {t.status}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

