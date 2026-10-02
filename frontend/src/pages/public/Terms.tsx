import React from 'react'

export const Terms: React.FC = () => {
  return (
    <div className="max-w-3xl mx-auto py-6 space-y-6 text-left">
      <h1 className="text-3xl font-black text-white">Terms of Service</h1>
      <p className="text-xs text-slate-400">Last updated: October 2026</p>

      <div className="space-y-4 text-xs text-slate-300 leading-relaxed bg-dark-card border border-dark-border p-6 rounded-2xl">
        <h3 className="text-sm font-bold text-white">1. Eligibility and Jurisdictional Restrictions</h3>
        <p>
          You must be at least 18 years of age to access and use our platform. The platform is not intended for users residing in states where skill-based gaming with stakes is legally restricted or prohibited, including but not limited to Andhra Pradesh, Telangana, Assam, Odisha, Nagaland, and Sikkim.
        </p>

        <h3 className="text-sm font-bold text-white">2. Provably Fair RNG System</h3>
        <p>
          All round outcomes in Aviator and Color Prediction are deterministically evaluated using client-side verifiable HMAC-SHA256 cryptography. The server seed hash is released prior to each round, making retroactive manipulation mathematically impossible.
        </p>

        <h3 className="text-sm font-bold text-white">3. Deposits and Withdrawals</h3>
        <p>
          All transactions are denominated in Indian National Rupees (INR) and processed internally in integer paise (1 INR = 100 paise). Withdrawals must match the KYC name registered to the account.
        </p>

        <h3 className="text-sm font-bold text-white">4. Responsible Gaming</h3>
        <p>
          Users are strongly encouraged to set daily deposit and session duration limits. Self-exclusion requests are irreversible for the duration selected.
        </p>
      </div>
    </div>
  )
}

