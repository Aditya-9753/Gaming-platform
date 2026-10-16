import React from 'react'
import { BrandLogo, isBuiltInBrand } from '../common/BrandLogo'
import { usePlatformConfig } from '../../hooks/usePlatformConfig'
import logoUrl from '../../assets/brand/runwin-logo.webp'
import './brand.css'

/** Big floating logo for the sign-in / sign-up cards (falls back to the text wordmark for custom brands). */
export const BrandHero: React.FC<{ className?: string }> = ({ className = 'w-48' }) => {
  const { platform_name: name, platform_logo_url: logo } = usePlatformConfig()
  if (logo || !isBuiltInBrand(name)) {
    return <BrandLogo wordmark className="flex justify-center" textClassName="text-2xl font-black tracking-tight" />
  }
  return (
    <div className="rw-hero">
      <img src={logoUrl} alt={name} className={`h-auto ${className}`} draggable={false} />
    </div>
  )
}
