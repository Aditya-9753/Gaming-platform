import React from 'react'
import { ShieldAlert } from 'lucide-react'
import { useUIStore } from '../../store/ui.store'
import { Button } from './Button'

export const AgeGateModal: React.FC = () => {
  const { ageGateCleared, clearAgeGate } = useUIStore()

  if (ageGateCleared) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
      <div className="max-w-md w-full bg-dark-card border border-amber-500/30 rounded-2xl p-6 shadow-2xl text-center space-y-5">
        <div className="w-16 h-16 rounded-full bg-amber-500/10 border border-amber-500/20 mx-auto flex items-center justify-center text-amber-400">
          <ShieldAlert className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <span className="px-3 py-1 rounded-full text-xs font-black bg-amber-500/20 text-amber-400 border border-amber-500/30 inline-block uppercase tracking-wider">
            18+ Age Restricted
          </span>
          <h2 className="text-xl font-black text-white">Age & Jurisdiction Notice</h2>
          <p className="text-xs text-slate-400 leading-relaxed">
            You must be at least 18 years old and eligible to use this platform in your location. Please review the terms and local laws before playing.
          </p>
        </div>

        <div className="space-y-3 pt-2">
          <Button
            variant="primary"
            className="w-full text-sm font-bold"
            onClick={clearAgeGate}
          >
            I am 18+ and Agree to Terms
          </Button>
          <a
            href="https://google.com"
            className="block text-xs font-semibold text-slate-500 hover:text-slate-300 transition-colors"
          >
            Exit (Under 18)
          </a>
        </div>
      </div>
    </div>
  )
}
