import React from 'react'

export const Privacy: React.FC = () => {
  return (
    <div className="max-w-3xl mx-auto py-6 space-y-6 text-left">
      <h1 className="text-3xl font-black text-white">Privacy Policy</h1>
      <p className="text-xs text-slate-400">Last updated: October 2026</p>

      <div className="space-y-4 text-xs text-slate-300 leading-relaxed bg-dark-card border border-dark-border p-6 rounded-2xl">
        <h3 className="text-sm font-bold text-white">1. Information We Collect</h3>
        <p>
          We collect personal credentials including phone numbers, email addresses, and verification documents strictly for fraud prevention, KYC verification, and payout processing in compliance with Indian regulatory standards.
        </p>

        <h3 className="text-sm font-bold text-white">2. Token Security & Storage</h3>
        <p>
          Authentication tokens are held in volatile memory and never persisted in unencrypted client-side web storage. Refresh tokens are transmitted strictly via secure, httpOnly, SameSite cookies.
        </p>

        <h3 className="text-sm font-bold text-white">3. Data Sharing</h3>
        <p>
          We do not sell user data. Information is only transmitted to certified payment aggregators (e.g. Razorpay/UPI gateway) to process deposits and withdrawals.
        </p>
      </div>
    </div>
  )
}

