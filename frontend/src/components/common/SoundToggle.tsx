import React, { useEffect, useState } from 'react'
import { Volume2, VolumeX } from 'lucide-react'
import { isMuted, onMutedChange, playSound, setMuted } from '../../utils/sounds'

/** Header button that mutes / unmutes game sound effects. */
export const SoundToggle: React.FC<{ className?: string }> = ({ className = '' }) => {
  const [muted, setState] = useState(isMuted())
  useEffect(() => onMutedChange(setState), [])
  const toggle = () => {
    const next = !muted
    setMuted(next)
    if (!next) playSound('bet')
  }
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={muted ? 'Turn game sounds on' : 'Turn game sounds off'}
      aria-pressed={!muted}
      title={muted ? 'Sounds off' : 'Sounds on'}
      className={`rounded-lg p-2 text-slate-300 hover:bg-dark-elevated hover:text-white ${className}`}
    >
      {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
    </button>
  )
}
