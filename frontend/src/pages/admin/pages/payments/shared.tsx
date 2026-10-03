import React, { useEffect, useRef, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Modal } from '../../components/Modal'
import { Button } from '../../../../components/common/Button'
import { showToast } from '../../../../components/common/Toast'
import { adminPaymentsApi, registerStepUpPrompt, StepUpCancelled, type HistoryRow } from '../../../../services/payments.api'
import { useAuthStore } from '../../../../store/auth.store'
import { getApiErrorMessage } from '../../../../utils/apiError'
import { formatDateTime } from '../../../../utils/formatters'

export { StatusPill } from '../../../../components/payments/StatusPill'

export const inputCls = 'w-full rounded-xl border border-dark-border bg-dark-elevated px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-purple-500 focus:outline-none'

/** Toast for a failed admin action (silent when the admin closed the verification dialog). */
export function actionFailed(title: string, error: unknown) {
  if (error instanceof StepUpCancelled) return
  showToast({ title, message: getApiErrorMessage(error, 'Please try again.'), type: 'error' })
}

export const ago = (iso: string | null | undefined) => {
  if (!iso) return '-'
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ${mins % 60}m ago`
  return `${Math.floor(mins / 1440)}d ago`
}

export const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
    <div className="break-all text-sm text-slate-200">{children}</div>
  </div>
)

export const Timeline: React.FC<{ rows?: HistoryRow[] }> = ({ rows }) => (
  <ol className="space-y-2 border-l border-dark-border pl-4">
    {(rows ?? []).map((h, i) => (
      <li key={i} className="text-xs">
        <p className="font-bold text-white">{h.from ? `${h.from} → ` : ''}{h.to}</p>
        <p className="text-slate-400">{h.actor} ({h.actor_type}) · {formatDateTime(h.at)}{h.ip ? ` · ${h.ip}` : ''}</p>
        {h.reason && <p className="text-slate-300">{h.reason}</p>}
      </li>
    ))}
  </ol>
)

/**
 * Asks for the 6-digit code whenever a money-moving call needs fresh verification.
 * Mounted once by the Payments page; it plugs itself into withStepUp().
 */
export const StepUpDialog: React.FC = () => {
  const usesEmail = useAuthStore((s) => s.user?.has2FA) // method is resolved server-side; email button is harmless for TOTP users
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState<string | undefined>()
  const [code, setCode] = useState('')
  const [sending, setSending] = useState(false)
  const resolver = useRef<((v: string | null) => void) | null>(null)

  useEffect(() => {
    registerStepUpPrompt((msg) => new Promise<string | null>((resolve) => {
      resolver.current = resolve
      setMessage(msg)
      setCode('')
      setOpen(true)
    }))
    return () => registerStepUpPrompt(null)
  }, [])

  const finish = (value: string | null) => {
    setOpen(false)
    resolver.current?.(value)
    resolver.current = null
  }

  const sendEmail = async () => {
    setSending(true)
    try {
      const r = await adminPaymentsApi.sendStepUpEmail()
      showToast({ title: 'Code sent', message: `Check ${r.sent_to}`, type: 'success' })
    } catch (error) {
      showToast({ title: 'Could not send code', message: getApiErrorMessage(error, 'Use your authenticator app.'), type: 'error' })
    } finally { setSending(false) }
  }

  return (
    <Modal open={open} title="Confirm it's you" onClose={() => finish(null)}>
      <div className="space-y-3">
        <p className="flex items-start gap-2 text-xs text-slate-400"><ShieldCheck className="h-4 w-4 shrink-0 text-purple-400" />Payment actions need a fresh two-step code. It stays valid for 5 minutes.</p>
        {message && <p className="text-xs font-bold text-rose-300">{message}</p>}
        <input
          autoFocus className={`${inputCls} text-center font-mono text-2xl tracking-[0.5em]`} inputMode="numeric" maxLength={6}
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          onKeyDown={(e) => { if (e.key === 'Enter' && code.length === 6) finish(code) }} placeholder="000000"
        />
        <div className="flex items-center justify-between gap-2">
          {usesEmail ? <button type="button" onClick={sendEmail} disabled={sending} className="text-xs font-bold text-purple-400 hover:underline">Email me a code</button> : <span />}
          <Button variant="accent" onClick={() => finish(code)} disabled={code.length !== 6}>Verify</Button>
        </div>
      </div>
    </Modal>
  )
}
