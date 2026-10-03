import axios from 'axios'
import { apiClient } from './api'

// ── Player side ───────────────────────────────────────────────────────────────

export type DepositStatus = 'PENDING' | 'SUCCESS' | 'REJECTED'
export type WithdrawalStatus = 'PENDING' | 'COMPLETED' | 'REJECTED'

export interface PaymentTarget {
  payee_name: string
  upi_id: string
  bank_name: string | null
  upi_link: string
  qr: string | null
  qr_image: string | null
}

export interface Deposit {
  id: string
  reference: string
  amount_paise: number
  credited_amount_paise: number | null
  status: DepositStatus
  stage: string
  utr: string | null
  note: string | null
  created_at: string
  expires_at: string
  credited_at: string | null
  can_submit_utr: boolean
  can_cancel: boolean
  payment?: PaymentTarget
}

export interface Withdrawal {
  id: string
  amount_paise: number
  status: WithdrawalStatus
  stage: string
  payout_to: string
  payout_reference: string | null
  reject_reason: string | null
  created_at: string
  completed_at: string | null
  can_cancel: boolean
}

export interface Beneficiary {
  id: string
  method: 'BANK' | 'UPI'
  holder_name: string
  bank_name: string | null
  masked: string
  cooling_until: string
  created_at: string
}

export interface Eligibility {
  available_paise: number
  pending_withdrawal_paise: number
  min_paise: number
  max_paise: number
  daily_count_left: number
  daily_amount_left_paise: number
  deposited_paise: number
  wagered_paise: number
  turnover_required_paise: number
  pin_set: boolean
  pin_cooling_until: string | null
  cooling_hours: number
  blockers: string[]
  can_withdraw: boolean
}

export interface PaymentConfig {
  enabled: boolean
  deposit_min_paise: number
  deposit_max_paise: number
  deposit_expiry_minutes: number
  unique_paise: boolean
}

interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export const paymentsApi = {
  config: async () => (await apiClient.get<PaymentConfig>('/payments/config')).data,
  createDeposit: async (amountPaise: number, key: string) =>
    (await apiClient.post<Deposit>('/payments/deposits', { amount_paise: amountPaise }, { headers: { 'Idempotency-Key': key } })).data,
  deposits: async (page = 1) => (await apiClient.get<Page<Deposit>>('/payments/deposits', { params: { page, page_size: 20 } })).data,
  deposit: async (id: string) => (await apiClient.get<Deposit>(`/payments/deposits/${id}`)).data,
  submitUtr: async (id: string, utr: string) => (await apiClient.post<Deposit>(`/payments/deposits/${id}/utr`, { utr })).data,
  cancelDeposit: async (id: string) => (await apiClient.post<Deposit>(`/payments/deposits/${id}/cancel`)).data,

  setPin: async (pin: string, password: string) => { await apiClient.post('/payments/pin', { pin, password }) },
  beneficiaries: async () => (await apiClient.get<Beneficiary[]>('/payments/beneficiaries')).data,
  addBeneficiary: async (body: Record<string, string>) => (await apiClient.post<Beneficiary>('/payments/beneficiaries', body)).data,
  removeBeneficiary: async (id: string) => { await apiClient.delete(`/payments/beneficiaries/${id}`) },

  eligibility: async () => (await apiClient.get<Eligibility>('/payments/withdrawals/eligibility')).data,
  requestWithdrawal: async (amountPaise: number, beneficiaryId: string, pin: string, key: string) =>
    (await apiClient.post<Withdrawal>('/payments/withdrawals', { amount_paise: amountPaise, beneficiary_id: beneficiaryId, pin },
      { headers: { 'Idempotency-Key': key } })).data,
  withdrawals: async (page = 1) => (await apiClient.get<Page<Withdrawal>>('/payments/withdrawals', { params: { page, page_size: 20 } })).data,
  cancelWithdrawal: async (id: string) => (await apiClient.post<Withdrawal>(`/payments/withdrawals/${id}/cancel`)).data,
}

// ── Staff side ────────────────────────────────────────────────────────────────

export interface AdminDeposit extends Deposit {
  state: string
  user_id: string
  username: string | null
  payment_account_id: string
  account_label: string | null
  account_owner: string | null
  verification_method: string | null
  verified_by: string | null
  bank_credit_id: string | null
  request_ip: string | null
  version: number
  history?: HistoryRow[]
  bank_credit?: BankCredit | null
  candidate_credits?: BankCredit[]
  can_act?: boolean
}

export interface AdminWithdrawal extends Withdrawal {
  state: string
  user_id: string
  username: string | null
  risk_score: number
  risk_flags: Record<string, unknown>
  initiated_by: string | null
  initiated_by_id: string | null
  initiated_at: string | null
  completed_by: string | null
  rejected_by: string | null
  admin_note: string | null
  request_ip: string | null
  version: number
  high_value: boolean
  history?: HistoryRow[]
  player?: Record<string, number>
}

export interface HistoryRow { from: string | null; to: string; actor: string; actor_type: string; reason: string | null; ip: string | null; at: string }

export interface BankCredit {
  id: string
  source: string
  provider: string | null
  utr: string
  amount_paise: number
  payment_account_id: string | null
  account_label: string | null
  remark: string | null
  payer_name: string | null
  payer_vpa: string | null
  status: 'UNMATCHED' | 'MATCHED' | 'IGNORED'
  deposit_id: string | null
  created_by: string | null
  received_at: string | null
  created_at: string
}

export interface CollectionAccount {
  id: string
  label: string
  upi_id: string
  payee_name: string
  bank_name: string | null
  has_qr_image: boolean
  qr_image: string | null
  status: 'PENDING_APPROVAL' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  owner_id: string
  owner: string | null
  approved_by: string | null
  review_note: string | null
  min_amount_paise: number
  max_amount_paise: number
  daily_limit_paise: number
  received_today_paise: number
  open_paise: number
  created_at: string
}

export interface PaymentSummary {
  scope: 'all' | 'own_accounts'
  is_super: boolean
  deposits: {
    by_state: Record<string, number>
    needs_review: number
    awaiting_payment: number
    credited_today_paise: number
    credited_today_count: number
    oldest_review_at: string | null
    unmatched_bank_credits: number
  }
  withdrawals: {
    open_count: number
    open_paise: number
    oldest_open_at: string | null
    paid_today_paise: number
    paid_today_count: number
    completed_per_admin_today: Array<{ admin: string; completed_today: number }>
  }
  accounts_pending_approval: number
}

// Step-up verification: money-moving admin calls need a fresh 2FA code.
// The token lives only in memory (never storage) and expires after ~5 minutes.
let stepUpToken: { token: string; exp: number } | null = null
let codePrompt: ((message?: string) => Promise<string | null>) | null = null

/** The admin Payments page registers its code dialog here. */
export function registerStepUpPrompt(fn: typeof codePrompt) { codePrompt = fn }

const isStepUpError = (error: unknown) =>
  axios.isAxiosError(error) && error.response?.status === 403 &&
  (error.response.data as { error?: { code?: string } } | undefined)?.error?.code === 'STEP_UP_REQUIRED'

export class StepUpCancelled extends Error {}

/** Run a call with the step-up header; ask for a code when the server requires one. */
export async function withStepUp<T>(call: (headers: Record<string, string>) => Promise<T>): Promise<T> {
  const headers = () => (stepUpToken && stepUpToken.exp > Date.now() ? { 'X-Step-Up-Token': stepUpToken.token } : {} as Record<string, string>)
  try {
    return await call(headers())
  } catch (error) {
    if (!isStepUpError(error)) throw error
  }
  stepUpToken = null
  let message: string | undefined
  for (let attempt = 0; attempt < 3; attempt++) {
    const code = codePrompt ? await codePrompt(message) : null
    if (!code) throw new StepUpCancelled('Verification cancelled')
    try {
      const { data } = await apiClient.post<{ token: string; expires_in: number }>('/admin/payments/step-up', { code })
      stepUpToken = { token: data.token, exp: Date.now() + (data.expires_in - 15) * 1000 }
      return await call(headers())
    } catch (error) {
      if (isStepUpError(error) || (axios.isAxiosError(error) && Boolean(error.config?.url?.endsWith('/step-up')))) {
        message = 'That code did not work — try again.'
        continue
      }
      throw error
    }
  }
  throw new StepUpCancelled('Too many wrong codes')
}

export const adminPaymentsApi = {
  sendStepUpEmail: async () => (await apiClient.post<{ sent_to: string; resend_in: number }>('/admin/payments/step-up/send')).data,
  summary: async () => (await apiClient.get<PaymentSummary>('/admin/payments/summary')).data,
  lookup: async (q: string) =>
    (await apiClient.get<{ deposits: AdminDeposit[]; withdrawals: AdminWithdrawal[]; bank_credits: BankCredit[] }>('/admin/payments/lookup', { params: { q } })).data,
  integrity: async () => (await apiClient.get<{ ok: boolean; problems: Array<Record<string, unknown>>; totals: Record<string, number> }>('/admin/payments/integrity')).data,

  accounts: async () => (await apiClient.get<CollectionAccount[]>('/admin/payments/accounts')).data,
  account: async (id: string) => (await apiClient.get<CollectionAccount>(`/admin/payments/accounts/${id}`)).data,
  createAccount: (body: Record<string, unknown>) =>
    withStepUp(async (headers) => (await apiClient.post<CollectionAccount>('/admin/payments/accounts', body, { headers })).data),
  updateAccount: (id: string, body: Record<string, unknown>) =>
    withStepUp(async (headers) => (await apiClient.patch<CollectionAccount>(`/admin/payments/accounts/${id}`, body, { headers })).data),
  reviewAccount: (id: string, approve: boolean, note?: string) =>
    withStepUp(async (headers) => (await apiClient.post<CollectionAccount>(`/admin/payments/accounts/${id}/review`, { approve, note }, { headers })).data),

  deposits: async (params: Record<string, string | number | undefined>) =>
    (await apiClient.get<Page<AdminDeposit>>('/admin/payments/deposits', { params })).data,
  deposit: async (id: string) => (await apiClient.get<AdminDeposit>(`/admin/payments/deposits/${id}`)).data,
  recheck: async (id: string) => (await apiClient.post<AdminDeposit>(`/admin/payments/deposits/${id}/recheck`)).data,
  confirm: (id: string, body: { utr: string; amount_paise?: number; note?: string }) =>
    withStepUp(async (headers) => (await apiClient.post<AdminDeposit>(`/admin/payments/deposits/${id}/confirm`, body, { headers })).data),
  rejectDeposit: async (id: string, reason: string) => (await apiClient.post<AdminDeposit>(`/admin/payments/deposits/${id}/reject`, { reason })).data,
  reverse: (id: string, reason: string) =>
    withStepUp(async (headers) => (await apiClient.post<AdminDeposit>(`/admin/payments/deposits/${id}/reverse`, { reason }, { headers })).data),

  credits: async (params: Record<string, string | number | undefined>) =>
    (await apiClient.get<Page<BankCredit>>('/admin/payments/bank-credits', { params })).data,
  importCredits: (accountId: string, lines: Array<Record<string, unknown>>) =>
    withStepUp(async (headers) => (await apiClient.post<{ created: number; matched: number; duplicates: string[]; errors: Array<{ line: number; error: string }>; matched_deposits: string[] }>(
      '/admin/payments/bank-credits/import', { account_id: accountId, lines }, { headers })).data),
  assignCredit: (creditId: string, depositId: string) =>
    withStepUp(async (headers) => (await apiClient.post<AdminDeposit>(`/admin/payments/bank-credits/${creditId}/assign`, { deposit_id: depositId }, { headers })).data),
  ignoreCredit: async (creditId: string, reason: string) => (await apiClient.post<BankCredit>(`/admin/payments/bank-credits/${creditId}/ignore`, { reason })).data,

  withdrawals: async (params: Record<string, string | number | undefined>) =>
    (await apiClient.get<Page<AdminWithdrawal>>('/admin/payments/withdrawals', { params })).data,
  withdrawal: async (id: string) => (await apiClient.get<AdminWithdrawal>(`/admin/payments/withdrawals/${id}`)).data,
  payoutDetails: (id: string) =>
    withStepUp(async (headers) => (await apiClient.post<Record<string, string | null>>(`/admin/payments/withdrawals/${id}/payout-details`, {}, { headers })).data),
  initiate: (id: string, note: string, version: number) =>
    withStepUp(async (headers) => (await apiClient.post<AdminWithdrawal>(`/admin/payments/withdrawals/${id}/initiate`, { note: note || undefined, expected_version: version }, { headers })).data),
  complete: (id: string, payoutReference: string, version: number, note?: string) =>
    withStepUp(async (headers) => (await apiClient.post<AdminWithdrawal>(`/admin/payments/withdrawals/${id}/complete`,
      { payout_reference: payoutReference, expected_version: version, note: note || undefined }, { headers })).data),
  rejectWithdrawal: (id: string, reason: string, version: number) =>
    withStepUp(async (headers) => (await apiClient.post<AdminWithdrawal>(`/admin/payments/withdrawals/${id}/reject`, { reason, expected_version: version }, { headers })).data),
}
