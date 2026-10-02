import React from 'react'

/** Purple skull bomb with a lit fuse (GameZone original art). */
export const SkullBomb: React.FC<{ className?: string; lit?: boolean }> = ({ className, lit = true }) => (
  <svg viewBox="0 0 100 100" className={className} aria-hidden>
    <defs>
      <radialGradient id="bombBody" cx="38%" cy="35%" r="70%">
        <stop offset="0%" stopColor="#c4a5ff" />
        <stop offset="45%" stopColor="#7c3aed" />
        <stop offset="100%" stopColor="#3b0f7a" />
      </radialGradient>
      <radialGradient id="spark" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#fff7c2" />
        <stop offset="40%" stopColor="#fbbf24" />
        <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
      </radialGradient>
    </defs>
    <path d="M66 22 C72 12, 80 12, 84 8" stroke="#d97706" strokeWidth="4" fill="none" strokeLinecap="round" />
    <rect x="58" y="20" width="16" height="12" rx="4" transform="rotate(35 66 26)" fill="#5b21b6" stroke="#2e1065" strokeWidth="2" />
    <circle cx="52" cy="58" r="34" fill="url(#bombBody)" stroke="#2e1065" strokeWidth="2.5" />
    <ellipse cx="40" cy="44" rx="10" ry="6" fill="#fff" opacity="0.35" transform="rotate(-30 40 44)" />
    {/* skull */}
    <path d="M38 52 a14 13 0 0 1 28 0 v6 a4 4 0 0 1 -4 4 h-2 v5 h-16 v-5 h-2 a4 4 0 0 1 -4 -4z" fill="#ede9fe" stroke="#4c1d95" strokeWidth="1.5" />
    <circle cx="46" cy="55" r="3.6" fill="#4c1d95" />
    <circle cx="58" cy="55" r="3.6" fill="#4c1d95" />
    <path d="M51 60 l1 2.5 l1 -2.5z" fill="#4c1d95" />
    <path d="M47 67 v-3 M51 67 v-3 M55 67 v-3" stroke="#4c1d95" strokeWidth="1.4" />
    {lit && <circle cx="86" cy="7" r="9" fill="url(#spark)" className="animate-pulse" />}
  </svg>
)

/** Faceted gold gem. */
export const GoldGem: React.FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 100 100" className={className} aria-hidden>
    <defs>
      <linearGradient id="gemTop" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#fff7d6" />
        <stop offset="100%" stopColor="#fbbf24" />
      </linearGradient>
      <linearGradient id="gemBottom" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#f59e0b" />
        <stop offset="100%" stopColor="#b45309" />
      </linearGradient>
    </defs>
    <polygon points="22,38 34,20 66,20 78,38" fill="url(#gemTop)" stroke="#92400e" strokeWidth="2" />
    <polygon points="22,38 78,38 50,84" fill="url(#gemBottom)" stroke="#92400e" strokeWidth="2" />
    <polygon points="34,20 42,38 50,20 58,38 66,20" fill="#fde68a" opacity="0.8" />
    <polygon points="42,38 50,84 58,38" fill="#fcd34d" opacity="0.7" />
    <path d="M30 30 L36 24" stroke="#fff" strokeWidth="3" strokeLinecap="round" opacity="0.8" />
  </svg>
)
