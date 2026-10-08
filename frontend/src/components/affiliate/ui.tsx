import React, { useState } from 'react'
import { Check, Copy, Loader2, X } from 'lucide-react'
import { getApiErrorMessage } from '../../utils/apiError'
import { showToast } from '../common/Toast'

/** Small building blocks shared by the partner portal and the affiliate back office. */

export const cx = (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(' ')

export const usd = (value: string | number | null | undefined, sign = false): string => {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return '—'
  const text = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${n < 0 ? '-' : sign && n > 0 ? '+' : ''}${text} $`
}

export const pct = (rate: string | number | null | undefined) =>
  rate === null || rate === undefined ? '—' : `${(Number(rate) * 100).toFixed(Number(rate) * 100 % 1 ? 2 : 0)}%`

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export const dateOnly = (iso: string | null | undefined) =>
  iso ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

export const errorText = (e: unknown, fallback = 'Something went wrong') => getApiErrorMessage(e, fallback)

export const toastError = (e: unknown, title = 'Could not complete') =>
  showToast({ title, message: errorText(e), type: 'error', duration: 6000 })

export const Card: React.FC<{ title?: React.ReactNode; actions?: React.ReactNode; className?: string; children: React.ReactNode }> = ({
  title, actions, className, children,
}) => (
  <section className={cx('rounded-2xl border border-dark-border bg-dark-card p-4 sm:p-5', className)}>
    {(title || actions) && (
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        {title && <h3 className="text-sm font-extrabold text-white">{title}</h3>}
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    )}
    {children}
  </section>
)

export const Money: React.FC<{ value: string | number | null | undefined; className?: string; sign?: boolean }> = ({ value, className, sign }) => {
  const n = Number(value)
  return <span className={cx('tabular-nums', n < 0 ? 'text-rose-400' : '', className)}>{usd(value, sign)}</span>
}

const TONES: Record<string, string> = {
  green: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  red: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  blue: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  slate: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  purple: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
}

const STATUS_TONE: Record<string, string> = {
  ACTIVE: 'green', COMPLETED: 'green', PROCESSED: 'green', APPROVED: 'green', PUBLISHED: 'green', CLOSED: 'slate', SENT: 'green',
  PENDING: 'amber', UNDER_REVIEW: 'amber', PROCESSING: 'blue', OPEN: 'blue', RECEIVED: 'blue', HELD: 'amber', NEW: 'amber',
  IN_PROGRESS: 'blue', CLOSING: 'amber', DRAFT: 'slate', PAUSED: 'slate', ARCHIVED: 'slate', IGNORED: 'slate', INACTIVE: 'slate',
  REJECTED: 'red', FAILED: 'red', CANCELLED: 'slate', SUSPENDED: 'red', BLOCKED: 'red', REVERSED: 'red', FROZEN: 'red',
  HIGH: 'red', MEDIUM: 'amber', LOW: 'slate', CONFIRMED: 'red', DISMISSED: 'slate', REVIEWED: 'blue',
}

export const Badge: React.FC<{ children: React.ReactNode; tone?: string; status?: string }> = ({ children, tone, status }) => (
  <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
    TONES[tone || STATUS_TONE[status || String(children)] || 'slate'])}>
    {children}
  </span>
)

export const StatusDot: React.FC<{ status: string }> = ({ status }) => {
  const tone = STATUS_TONE[status] || 'slate'
  const color = { green: 'bg-emerald-400', red: 'bg-rose-400', amber: 'bg-amber-400', blue: 'bg-blue-400', slate: 'bg-slate-500', purple: 'bg-purple-400' }[tone]
  return <span className={cx('inline-block h-2.5 w-2.5 shrink-0 rounded-full', color)} title={status} aria-label={status} />
}

export const Spinner: React.FC<{ label?: string }> = ({ label }) => (
  <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400">
    <Loader2 className="h-4 w-4 animate-spin" /> {label || 'Loading…'}
  </div>
)

export const Empty: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <div className="rounded-xl border border-dashed border-dark-border px-4 py-8 text-center text-sm text-slate-400">{children || 'Nothing here yet'}</div>
)

export const Tabs: React.FC<{ tabs: Array<{ id: string; label: React.ReactNode }>; value: string; onChange: (id: string) => void }> = ({ tabs, value, onChange }) => (
  <div className="flex gap-1 overflow-x-auto rounded-xl border border-dark-border bg-dark-bg/60 p-1" role="tablist">
    {tabs.map((tab) => (
      <button key={tab.id} type="button" role="tab" aria-selected={value === tab.id} onClick={() => onChange(tab.id)}
        className={cx('min-h-[40px] whitespace-nowrap rounded-lg px-3 text-xs font-bold transition',
          value === tab.id ? 'bg-brand-blue text-white' : 'text-slate-400 hover:text-white')}>
        {tab.label}
      </button>
    ))}
  </div>
)

export const Field: React.FC<{ label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }> = ({ label, hint, children, className }) => (
  <label className={cx('block space-y-1', className)}>
    <span className="text-[11px] font-bold uppercase tracking-wide text-slate-400">{label}</span>
    {children}
    {hint && <span className="block text-[11px] text-slate-500">{hint}</span>}
  </label>
)

export const inputCls =
  'w-full min-h-[44px] rounded-xl border border-dark-border bg-dark-bg px-3 text-sm text-white placeholder-slate-500 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue'

export const Btn: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'ghost' | 'danger' | 'success'; busy?: boolean; small?: boolean }> = ({
  tone = 'primary', busy, small, className, children, disabled, ...rest
}) => (
  <button type="button" disabled={disabled || busy} {...rest}
    className={cx('inline-flex items-center justify-center gap-1.5 rounded-xl font-extrabold transition disabled:cursor-not-allowed disabled:opacity-50',
      small ? 'min-h-[36px] px-3 text-xs' : 'min-h-[44px] px-4 text-sm',
      tone === 'primary' && 'bg-brand-blue text-white hover:brightness-110',
      tone === 'ghost' && 'border border-dark-border text-slate-200 hover:border-slate-500 hover:text-white',
      tone === 'danger' && 'bg-rose-600 text-white hover:bg-rose-500',
      tone === 'success' && 'bg-emerald-600 text-white hover:bg-emerald-500',
      className)}>
    {busy && <Loader2 className="h-4 w-4 animate-spin" />}
    {children}
  </button>
)

export const CopyButton: React.FC<{ text: string; label?: string; small?: boolean }> = ({ text, label, small = true }) => {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const area = document.createElement('textarea')
      area.value = text
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      area.remove()
    }
    setDone(true)
    setTimeout(() => setDone(false), 1500)
  }
  return (
    <Btn tone="ghost" small={small} onClick={copy} aria-label={`Copy ${label || ''}`.trim()}>
      {done ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      {label && <span>{done ? 'Copied' : label}</span>}
    </Btn>
  )
}

export const Modal: React.FC<{ open: boolean; title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }> = ({ open, title, onClose, children, wide }) => {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}
      onClick={onClose}>
      <div className={cx('max-h-[92dvh] w-full overflow-y-auto rounded-t-3xl border border-dark-border bg-dark-card p-5 shadow-2xl sm:rounded-3xl',
        wide ? 'sm:max-w-3xl' : 'sm:max-w-md')} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-black text-white">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-2 text-slate-400 hover:bg-dark-elevated hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** Simple "are you sure?" step before an action. */
export const ConfirmPrompt: React.FC<{ open: boolean; title?: string; message?: string; onClose: () => void; onConfirm: () => Promise<void> }> = ({
  open, title = 'Confirm', message, onClose, onConfirm,
}) => {
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} title={title} onClose={onClose}>
      {message && <p className="mb-4 text-sm text-slate-300">{message}</p>}
      <div className="flex gap-2">
        <Btn tone="ghost" className="flex-1" onClick={onClose}>Cancel</Btn>
        <Btn className="flex-1" busy={busy} onClick={async () => {
          setBusy(true)
          try { await onConfirm() } finally { setBusy(false) }
        }}>Confirm</Btn>
      </div>
    </Modal>
  )
}

export function useAsync<T>(loader: () => Promise<T>, deps: React.DependencyList = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const reload = React.useCallback(async () => {
    setLoading(true)
    try {
      setData(await loader())
      setError(null)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  React.useEffect(() => { void reload() }, [reload])
  return { data, error, loading, reload, setData }
}

export const ErrorBox: React.FC<{ message: string; onRetry?: () => void }> = ({ message, onRetry }) => (
  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
    <p>{message}</p>
    {onRetry && <Btn tone="ghost" small className="mt-3" onClick={onRetry}>Retry</Btn>}
  </div>
)

export const Table: React.FC<{ head: React.ReactNode[]; children: React.ReactNode; empty?: boolean; emptyText?: string }> = ({ head, children, empty, emptyText }) => (
  <div className="-mx-4 overflow-x-auto sm:mx-0">
    <table className="w-full min-w-[640px] text-left text-xs">
      <thead>
        <tr className="border-b border-dark-border text-[10px] uppercase tracking-wide text-slate-500">
          {head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 font-bold">{h}</th>)}
        </tr>
      </thead>
      <tbody className="divide-y divide-dark-border/60 text-slate-200">{children}</tbody>
    </table>
    {empty && <div className="px-4 py-8 text-center text-sm text-slate-500">{emptyText || 'Nothing to show'}</div>}
  </div>
)

export const Td: React.FC<React.TdHTMLAttributes<HTMLTableCellElement>> = ({ className, ...rest }) => (
  <td className={cx('whitespace-nowrap px-3 py-2.5 align-middle', className)} {...rest} />
)
