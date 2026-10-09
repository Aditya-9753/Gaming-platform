import React from 'react'
import { Languages } from 'lucide-react'
import { useUIStore } from '../../store/ui.store'

const OPTIONS: Array<{ code: 'en' | 'hi'; label: string; name: string }> = [
  { code: 'en', label: 'EN', name: 'English' },
  { code: 'hi', label: 'हिं', name: 'हिन्दी' },
]

/** English / Hindi switch; the whole site re-renders in the chosen language. */
export const LanguageSwitcher: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { locale, setLocale } = useUIStore()

  return (
    <div role="group" aria-label="Language / भाषा" className={`flex items-center gap-1.5 p-1 rounded-xl bg-dark-card border border-dark-border text-xs ${className}`}>
      <Languages className="w-3.5 h-3.5 text-slate-400 ml-1.5" aria-hidden />
      {OPTIONS.map((option) => (
        <button
          key={option.code}
          type="button"
          onClick={() => setLocale(option.code)}
          aria-pressed={locale === option.code}
          aria-label={option.name}
          lang={option.code}
          className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
            locale === option.code ? 'bg-brand-blue text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
