import React from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, HeartHandshake } from 'lucide-react'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'
import { t as tr } from '../../i18n'

export const Footer: React.FC = () => {
  const { platform_name: platformName } = usePlatformConfig()
  return (
    <footer className="bg-dark-card border-t border-dark-border text-slate-400 py-8 px-4 sm:px-6 pb-24 lg:pb-8">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-emerald-400 font-bold">
            <ShieldCheck className="w-4 h-4" />
            <span>{tr('Provably Fair RNG')}</span>
          </div>
          <div className="flex items-center gap-1.5 text-amber-400 font-bold">
            <HeartHandshake className="w-4 h-4" />
            <span>{tr('18+ Play Responsibly')}</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link to="/terms" className="hover:text-white transition-colors">
            {tr('Terms of Service')}
          </Link>
          <Link to="/privacy" className="hover:text-white transition-colors">
            {tr('Privacy Policy')}
          </Link>
          <Link to="/support" className="hover:text-white transition-colors">
            {tr('Support')}
          </Link>
        </div>

        <p className="text-slate-500 text-[11px]">
          © {new Date().getFullYear()} {platformName}. All rights reserved.
        </p>
      </div>
    </footer>
  )
}

