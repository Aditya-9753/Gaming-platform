import React, { useState, useEffect } from 'react'
import { CheckCircle2, AlertCircle, Info, X, AlertTriangle } from 'lucide-react'

export interface ToastMessage {
  id?: string
  title?: string
  message?: string
  type?: 'success' | 'error' | 'warning' | 'info'
  duration?: number
}

const TOAST_EVENT = 'app_toast_trigger'

export const showToast = (toast: ToastMessage) => {
  const event = new CustomEvent(TOAST_EVENT, {
    detail: { ...toast, id: crypto.randomUUID() },
  })
  window.dispatchEvent(event)
}

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<ToastMessage>
      const newToast = customEvent.detail
      setToasts((prev) => [...prev, newToast])

      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== newToast.id))
      }, newToast.duration || 4000)
    }

    window.addEventListener(TOAST_EVENT, handler)
    return () => window.removeEventListener(TOAST_EVENT, handler)
  }, [])

  const removeToast = (id?: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />,
    error: <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />,
    info: <Info className="w-5 h-5 text-cyan-400 shrink-0" />,
  }

  const borders = {
    success: 'border-emerald-500/30 bg-emerald-950/80',
    error: 'border-rose-500/30 bg-rose-950/80',
    warning: 'border-amber-500/30 bg-amber-950/80',
    info: 'border-cyan-500/30 bg-cyan-950/80',
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0">
      {toasts.map((toast) => {
        const type = toast.type || 'info'
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border backdrop-blur-md shadow-2xl animate-in slide-in-from-right-10 text-white transition-all ${borders[type]}`}
          >
            {icons[type]}
            <div className="flex-1 min-w-0">
              {toast.title && <h5 className="text-xs font-bold">{toast.title}</h5>}
              {toast.message && <p className="text-xs text-slate-300 mt-0.5 leading-relaxed">{toast.message}</p>}
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-400 hover:text-white p-0.5"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
