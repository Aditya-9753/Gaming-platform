import React from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, HeartHandshake } from 'lucide-react'

export const Footer: React.FC = () => {
  return (
    <footer className="bg-dark-card border-t border-dark-border text-slate-400 py-8 px-4 sm:px-6">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-emerald-400 font-bold">
            <ShieldCheck className="w-4 h-4" />
            <span>Provably Fair RNG</span>
          </div>
          <div className="flex items-center gap-1.5 text-amber-400 font-bold">
            <HeartHandshake className="w-4 h-4" />
            <span>18+ Play Responsibly</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link to="/terms" className="hover:text-white transition-colors">
            Terms of Service
          </Link>
          <Link to="/privacy" className="hover:text-white transition-colors">
            Privacy Policy
          </Link>
          <Link to="/support" className="hover:text-white transition-colors">
            Support
          </Link>
        </div>

        <p className="text-slate-500 text-[11px]">
          © {new Date().getFullYear()} GameZone. All rights reserved.
        </p>
      </div>
    </footer>
  )
}

