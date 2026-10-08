import { apiClient } from './api'
import type {
  BlogPost, Campaign, Contact, Deal, ExportJob, Faq, FilterOptions, Kpis, LedgerEntry, PartnerMe, PartnerNotification,
  Postback, PostbackLog, PrMaterial, PromoCode, QrCode, SeriesPoint, Source, Statement, StatRow, SubpartnerRow, TermsVersion,
  TrackingLink, WalletView, Withdrawal, WithdrawalMethod,
} from '../types/affiliate.types'

export interface StatsQuery {
  period: string
  date_from?: string
  date_to?: string
  source_ids?: number[]
  link_ids?: number[]
  countries?: string[]
}

const qs = (q: StatsQuery) => ({
  period: q.period,
  date_from: q.date_from || undefined,
  date_to: q.date_to || undefined,
  source_ids: q.source_ids?.length ? q.source_ids.join(',') : undefined,
  link_ids: q.link_ids?.length ? q.link_ids.join(',') : undefined,
  countries: q.countries?.length ? q.countries.join(',') : undefined,
})

const get = async <T>(url: string, params?: Record<string, unknown>) => (await apiClient.get<T>(url, { params })).data
const post = async <T>(url: string, body?: unknown, headers?: Record<string, string>) => (await apiClient.post<T>(url, body, { headers })).data
const patch = async <T>(url: string, body?: unknown) => (await apiClient.patch<T>(url, body)).data
const put = async <T>(url: string, body?: unknown) => (await apiClient.put<T>(url, body)).data

/** Partner portal API — the partner is always taken from the session, never sent. */
export const partnerApi = {
  // public
  config: () => get<{ app_android_url: string; app_ios_url: string; languages: string[]; min_payout: string; cookie_days: number; terms: TermsVersion | null }>('/aff/public/config'),
  terms: () => get<{ terms: TermsVersion | null }>('/aff/public/terms'),
  inviter: (code: string) => get<{ valid: boolean; partner_code: string | null }>(`/aff/public/inviter/${encodeURIComponent(code)}`),
  signup: (body: Record<string, unknown>) => post<{ partner_code: string; status: string }>('/aff/auth/signup', body),
  verifyEmail: (token: string) => post<{ verified: boolean; status: string | null }>('/aff/auth/verify-email', { token }),
  resendVerification: () => post<{ sent: boolean }>('/aff/auth/resend-verification'),
  trackClick: (body: Record<string, string | undefined>) =>
    post<{ tracked: boolean; click_id: string | null; cookie_days: number }>('/aff/track/click', body),

  // me / account
  me: () => get<PartnerMe>('/aff/me'),
  updateMe: (body: Record<string, unknown>) => patch<{ ok: boolean }>('/aff/me', body),
  acceptTerms: (version_id: number) => post('/aff/terms/accept', { version_id }),
  deal: () => get<{ current: Deal | null; history: Deal[] }>('/aff/me/deal'),
  changePassword: (body: { current_password: string; new_password: string }) => post('/aff/account/password', body),
  changeEmail: (body: { password: string; new_email: string }) => post('/aff/account/email', body),
  logoutAll: () => post('/auth/logout-all'),

  // dashboard & statistics
  summary: (q: StatsQuery) => get<Kpis>('/aff/dashboard/summary', qs(q)),
  timeseries: (q: StatsQuery) => get<{ timezone: string; series: SeriesPoint[] }>('/aff/dashboard/timeseries', qs(q)),
  filters: () => get<FilterOptions>('/aff/dashboard/filters'),
  statistics: (groupBy: string, q: StatsQuery) => get<{ items: StatRow[] }>('/aff/statistics/common', { group_by: groupBy, ...qs(q) }),
  subpartnerStats: (q: StatsQuery) => get<{ items: SubpartnerRow[] }>('/aff/statistics/subpartners', qs(q)),
  exportStats: (body: Record<string, unknown>) => post<ExportJob>('/aff/statistics/export', body),
  exports: () => get<{ items: ExportJob[] }>('/aff/exports'),
  downloadExport: async (id: number) => (await apiClient.get<Blob>(`/aff/exports/${id}/download`, { responseType: 'blob' })).data,

  // tracking
  sources: () => get<{ items: Source[] }>('/aff/sources'),
  createSource: (body: Record<string, unknown>) => post<Source>('/aff/sources', body),
  updateSource: (id: number, body: Record<string, unknown>) => patch<Source>(`/aff/sources/${id}`, body),
  campaigns: () => get<{ items: Campaign[] }>('/aff/campaigns'),
  createCampaign: (body: Record<string, unknown>) => post<Campaign>('/aff/campaigns', body),
  updateCampaign: (id: number, body: Record<string, unknown>) => patch<Campaign>(`/aff/campaigns/${id}`, body),
  links: () => get<{ items: TrackingLink[]; base_url: string; mirrors: string[] }>('/aff/tracking-links'),
  createLink: (body: Record<string, unknown>) => post<TrackingLink>('/aff/tracking-links', body),
  updateLink: (id: number, body: Record<string, unknown>) => patch<TrackingLink>(`/aff/tracking-links/${id}`, body),
  promos: () => get<{ items: PromoCode[] }>('/aff/promo-codes'),
  createPromo: (tracking_link_id: number, code?: string) => post<PromoCode>('/aff/promo-codes', { tracking_link_id, code: code || undefined }),

  // PR tools
  materials: (type?: string) => get<{ items: PrMaterial[] }>('/aff/pr-materials', { type }),
  qrCodes: () => get<{ items: QrCode[] }>('/aff/qr-codes'),
  createQr: (tracking_link_id: number, name?: string) => post<QrCode>('/aff/qr-codes', { tracking_link_id, name }),

  // wallet & withdrawals
  wallet: () => get<WalletView>('/aff/wallet'),
  transactions: (cursor?: number) => get<{ items: LedgerEntry[]; next_cursor: number | null }>('/aff/wallet/transactions', { cursor }),
  statements: () => get<{ items: Statement[] }>('/aff/wallet/statements'),
  methods: () => get<{ items: WithdrawalMethod[]; types: string[] }>('/aff/withdrawal-methods'),
  addMethod: (body: Record<string, unknown>) => post<WithdrawalMethod>('/aff/withdrawal-methods', body),
  updateMethod: (id: number, body: Record<string, unknown>) => patch<WithdrawalMethod>(`/aff/withdrawal-methods/${id}`, body),
  withdrawals: (cursor?: number) => get<{ items: Withdrawal[]; next_cursor: number | null }>('/aff/withdrawals', { cursor }),
  withdrawal: (id: number) => get<Withdrawal>(`/aff/withdrawals/${id}`),
  requestWithdrawal: (body: { amount: string; method_id?: number }, idempotencyKey: string) =>
    post<Withdrawal>('/aff/withdrawals', body, { 'Idempotency-Key': idempotencyKey }),
  cancelWithdrawal: (id: number) => post<Withdrawal>(`/aff/withdrawals/${id}/cancel`),
  autoWithdrawal: () => get<{ enabled: boolean; method_id: number | null; min_amount: string }>('/aff/withdrawals-auto'),
  setAutoWithdrawal: (body: { enabled: boolean; method_id?: number | null; min_amount?: string }) =>
    put<{ enabled: boolean; method_id: number | null; min_amount: string }>('/aff/withdrawals-auto', body),

  // subpartners
  subpartners: () => get<{ invite_link: string | null; rate: string; items: SubpartnerRow[] }>('/aff/subpartners'),

  // postbacks
  postbacks: () => get<{ items: Postback[]; logs: PostbackLog[]; macros: string[] }>('/aff/postbacks'),
  createPostback: (event_type: string, url_template: string) => post<Postback>('/aff/postbacks', { event_type, url_template }),
  updatePostback: (id: number, body: Record<string, unknown>) => patch<Postback>(`/aff/postbacks/${id}`, body),
  testPostback: (id: number) => post<{ url: string; status_code: number | null; error?: string }>(`/aff/postbacks/${id}/test`),

  // content & support
  faqs: () => get<{ items: Faq[] }>('/aff/faqs'),
  blog: () => get<{ items: BlogPost[] }>('/aff/blog-posts'),
  blogPost: (slug: string) => get<BlogPost>(`/aff/blog-posts/${encodeURIComponent(slug)}`),
  manager: () => get<{ manager: { name: string; email: string | null } | null }>('/aff/contacts/manager'),
  contacts: () => get<{ items: Contact[] }>('/aff/contacts'),
  sendContact: (body: Record<string, string>) => post<Contact>('/aff/contacts', body),
  notifications: () => get<{ items: PartnerNotification[] }>('/aff/notifications'),
  readNotifications: (ids?: string[]) => post('/aff/notifications/read', ids ?? null),
}
