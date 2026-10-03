import React from 'react'
import { Flame } from 'lucide-react'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'

/** Splits "Rudra247" into the word and a trailing number so the number can sit in a blue chip. */
const splitName = (name: string): [string, string] => {
  const match = name.match(/^(.*?)(\d+)$/)
  return match && match[1] ? [match[1], match[2]] : [name, '']
}

/**
 * Platform logo + name, both configurable by the super admin.
 * `wordmark` (site header, login) shows the name only, in white with the number on blue;
 * without it the original icon + name layout is kept (used inside game pages).
 */
export const BrandLogo: React.FC<{ className?: string; iconClassName?: string; textClassName?: string; showName?: boolean; wordmark?: boolean }> = ({
  className = 'flex items-center gap-2',
  iconClassName = 'w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 text-dark-bg',
  textClassName = 'text-lg font-black tracking-wide text-white',
  showName = true,
  wordmark = false,
}) => {
  const { platform_name: name, platform_logo_url: logo } = usePlatformConfig()

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
      {logo
        ? <img src={logo} alt="" className={`${iconClassName} object-contain bg-transparent`} />
        : <span className={`flex items-center justify-center ${iconClassName}`}><Flame className="w-5 h-5 fill-current" /></span>}
      {showName && <span className={textClassName}>{name.toUpperCase()}</span>}
    </span>
  )
}
