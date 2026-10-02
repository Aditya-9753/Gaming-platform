import React from 'react'
import { Languages } from 'lucide-react'
import { useUIStore } from '../../store/ui.store'

export const LanguageSwitcher: React.FC = () => {
  const { locale, setLocale } = useUIStore()

  return (
    <div className="flex items-center gap-1.5 p-1 rounded-xl bg-dark-card border border-dark-border text-xs">
      <Languages className="w-3.5 h-3.5 text-slate-400 ml-1.5" />
      <button
        onClick={() => setLocale('en')}
        className={`px-2 py-1 rounded-lg font-bold transition-all ${
          locale === 'en'
            ? 'bg-emerald-500 text-dark-bg'
            : 'text-slate-400 hover:text-white'
        }`}
      >
        EN
      </button>
      <button
        onClick={() => setLocale('hi')}
        className={`px-2 py-1 rounded-lg font-bold transition-all ${
          locale === 'hi'
            ? 'bg-emerald-500 text-dark-bg'
            : 'text-slate-400 hover:text-white'
        }`}
      >
        HI
      </button>
    </div>
  )
}

