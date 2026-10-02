import React from 'react'
import { Flame } from 'lucide-react'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'

/** Platform logo + name, both configurable by the super admin. */
export const BrandLogo: React.FC<{ className?: string; iconClassName?: string; textClassName?: string; showName?: boolean }> = ({
  className = 'flex items-center gap-2',
  iconClassName = 'w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 text-dark-bg',
  textClassName = 'text-lg font-black tracking-wide text-white',
  showName = true,
}) => {
  const { platform_name: name, platform_logo_url: logo } = usePlatformConfig()
  return (
    <span className={className}>
      {logo
        ? <img src={logo} alt="" className={`${iconClassName} object-contain bg-transparent`} />
        : <span className={`flex items-center justify-center ${iconClassName}`}><Flame className="w-5 h-5 fill-current" /></span>}
      {showName && <span className={textClassName}>{name.toUpperCase()}</span>}
    </span>
  )
}
