import React from 'react'
import { Flame } from 'lucide-react'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'
import markUrl from '../../assets/brand/rudrawin-mark.webp'
import wordUrl from '../../assets/brand/rudrawin-wordmark.webp'
import '../brand/brand.css'

/** Splits "Rudra247" into the word and a trailing number so the number can sit in a blue chip. */
const splitName = (name: string): [string, string] => {
  const match = name.match(/^(.*?)(\d+)$/)
  return match && match[1] ? [match[1], match[2]] : [name, '']
}

/** The built-in artwork spells RUDRAWIN, so it is only used while the brand name matches. */
const isRudraWin = (name: string) => /^rudra\s*win$/i.test(name.trim())

/**
 * Platform logo + name, both configurable by the super admin.
 * `wordmark` (site header) shows the brand mark + name; without it the icon + name layout
 * is kept (used inside game pages). With no custom logo URL and the RudraWin name, the
 * built-in RudraWin artwork is used.
 */
export const BrandLogo: React.FC<{ className?: string; iconClassName?: string; textClassName?: string; showName?: boolean; wordmark?: boolean }> = ({
  className = 'flex items-center gap-2',
  iconClassName = 'w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 text-dark-bg',
  textClassName = 'text-lg font-black tracking-wide text-white',
  showName = true,
  wordmark = false,
}) => {
  const { platform_name: name, platform_logo_url: logo } = usePlatformConfig()
  const builtIn = !logo && isRudraWin(name)

  if (wordmark && builtIn) {
    return (
      <span className={`${className} rw-brand`} aria-label={name}>
        <img src={markUrl} alt="" className="rw-brand__mark h-8 w-auto sm:h-9" draggable={false} />
        <img src={wordUrl} alt="" className="h-4 w-auto sm:h-5" draggable={false} />
      </span>
    )
  }

  if (wordmark) {
    const [word, number] = splitName(name.toUpperCase())
    return (
      <span className={className}>
        {logo && <img src={logo} alt="" className={`${iconClassName} object-contain bg-transparent`} />}
        <span className={`inline-flex items-center gap-1 ${textClassName}`} aria-label={name}>
          <span className="text-white">{word}</span>
          {number && <span className="rounded-md bg-blue-600 px-1.5 py-0.5 leading-none text-white not-italic">{number}</span>}
        </span>
      </span>
    )
  }

  return (
    <span className={className}>
      {logo || builtIn
        ? <img src={logo || markUrl} alt="" className={`${iconClassName} object-contain bg-transparent`} />
        : <span className={`flex items-center justify-center ${iconClassName}`}><Flame className="w-5 h-5 fill-current" /></span>}
      {showName && <span className={textClassName}>{name.toUpperCase()}</span>}
    </span>
  )
}
