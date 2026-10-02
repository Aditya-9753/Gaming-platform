import React from 'react'
import { ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

export interface ProvablyFairBadgeProps {
  className?: string
  showLink?: boolean
}

export const ProvablyFairBadge: React.FC<ProvablyFairBadgeProps> = ({
  className = '',
  showLink = true,
}) => {
  const content = (
    <div
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs font-bold hover:bg-cyan-500/20 transition-all ${className}`}
    >
      <ShieldCheck className="w-4 h-4 shrink-0" />
      <span>Provably Fair (HMAC-SHA256)</span>
    </div>
  )

  if (showLink) {
    return <Link to="/fairness">{content}</Link>
  }

  return content
}

