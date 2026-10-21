import { showToast } from '../../../../components/common/toastBus'
import { StepUpCancelled } from '../../../../services/payments.api'
import { getApiErrorMessage } from '../../../../utils/apiError'

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
