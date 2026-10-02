import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Ban, CheckCircle2, Coins } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { showToast } from '../../../components/common/Toast'
import { formatPaiseToRupee } from '../../../utils/formatters'

export const UserDetails: React.FC = () => {
  const { id } = useParams()
  const [isSuspended, setIsSuspended] = useState(false)
  const [kycStatus, setKycStatus] = useState<'verified' | 'pending' | 'rejected'>('verified')

  const toggleSuspend = () => {
    setIsSuspended(!isSuspended)
    showToast({
      title: isSuspended ? 'User Re-activated' : 'User Suspended',
      message: `Account status updated for ${id}`,
      type: isSuspended ? 'success' : 'warning',
    })
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <Link
        to="/admin/users"
        className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to User List</span>
      </Link>

      <div className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-purple-500/20 text-purple-400 flex items-center justify-center text-xl font-bold">
              U
            </div>
            <div>
              <h2 className="text-xl font-black text-white">Player: {id}</h2>
              <span className="text-xs text-slate-400">+91 9876543210 • rohit@example.com</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant={isSuspended ? 'primary' : 'danger'}
              size="sm"
              onClick={toggleSuspend}
              leftIcon={<Ban className="w-3.5 h-3.5" />}
            >
              {isSuspended ? 'Unsuspend User' : 'Suspend Account'}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3.5 rounded-xl bg-dark-elevated border border-dark-border text-center">
            <span className="text-xs text-slate-400 block mb-1">Real Balance</span>
            <span className="text-base font-black font-mono text-emerald-400">
              {formatPaiseToRupee(545000)}
            </span>
          </div>
          <div className="p-3.5 rounded-xl bg-dark-elevated border border-dark-border text-center">
            <span className="text-xs text-slate-400 block mb-1">KYC Status</span>
            <span className="text-base font-black text-white capitalize">{kycStatus}</span>
          </div>
          <div className="p-3.5 rounded-xl bg-dark-elevated border border-dark-border text-center">
            <span className="text-xs text-slate-400 block mb-1">Total Bets</span>
            <span className="text-base font-black text-white">284</span>
          </div>
          <div className="p-3.5 rounded-xl bg-dark-elevated border border-dark-border text-center">
            <span className="text-xs text-slate-400 block mb-1">VIP Rank</span>
            <span className="text-base font-black text-amber-400">Gold</span>
          </div>
        </div>

        <div className="space-y-3 pt-3 border-t border-dark-border">
          <h4 className="text-sm font-bold text-white">Administrative Actions</h4>
          <div className="flex gap-2">
            <Link to={`/admin/wallet-adjustment?userId=${id}`}>
              <Button variant="secondary" size="sm" leftIcon={<Coins className="w-4 h-4" />}>
                Manual Wallet Adjustment
              </Button>
            </Link>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setKycStatus('verified')
                showToast({ title: 'KYC Approved', type: 'success' })
              }}
              leftIcon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
            >
              Approve KYC Documents
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
