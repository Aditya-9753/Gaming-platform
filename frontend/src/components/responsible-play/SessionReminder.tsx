import React, { useState, useEffect } from 'react'
import { Clock } from 'lucide-react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { t as tr } from '../../i18n'

export interface SessionReminderProps {
  sessionLimitMinutes?: number
}

export const SessionReminder: React.FC<SessionReminderProps> = ({
  sessionLimitMinutes = 60,
}) => {
  const [elapsedMinutes, setElapsedMinutes] = useState(0)
  const [showAlert, setShowAlert] = useState(false)

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedMinutes((prev) => {
        const next = prev + 1
        if (next >= sessionLimitMinutes && next % sessionLimitMinutes === 0) {
          setShowAlert(true)
        }
        return next
      })
    }, 60000)

    return () => clearInterval(timer)
  }, [sessionLimitMinutes])

  return (
    <>
      {showAlert && (
        <Modal isOpen={showAlert} onClose={() => setShowAlert(false)} maxWidth="sm">
          <div className="text-center space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 mx-auto flex items-center justify-center text-amber-400">
              <Clock className="w-7 h-7" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">{tr('Time Check Reminder')}</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                You have been playing continuously for{' '}
                <span className="text-white font-bold">{elapsedMinutes} minutes</span>{tr('. Take a break, stay hydrated, and play responsibly.')}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="primary"
                className="w-full font-bold"
                onClick={() => setShowAlert(false)}
              >
                I Understand, Continue
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Subtle indicator in corner */}
      {elapsedMinutes > 0 && (
        <div className="hidden sm:flex fixed bottom-3 left-3 z-30 items-center gap-1.5 px-2.5 py-1 rounded-lg bg-dark-card/80 border border-dark-border text-[10px] text-slate-400 backdrop-blur-sm">
          <Clock className="w-3 h-3 text-emerald-400" />
          <span>Session: {elapsedMinutes}m</span>
        </div>
      )}
    </>
  )
}
