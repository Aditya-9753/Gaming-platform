export interface ToastMessage {
  id?: string
  title?: string
  message?: string
  type?: 'success' | 'error' | 'warning' | 'info'
  duration?: number
}

export const TOAST_EVENT = 'app_toast_trigger'

export const showToast = (toast: ToastMessage) => {
  const event = new CustomEvent(TOAST_EVENT, {
    detail: { ...toast, id: crypto.randomUUID() },
  })
  window.dispatchEvent(event)
}
